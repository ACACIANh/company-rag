from shared.fga.base import PermissionCacheBackend
from shared.fga.models import FGAConfig, UserPermission


class FGAClient:
    def __init__(
        self,
        config: FGAConfig,
        cache: PermissionCacheBackend,
        pg_pool=None,   # asyncpg.Pool | None
    ) -> None:
        self._config = config
        self._cache = cache
        self._pg_pool = pg_pool

    # ── 순수 함수 ────────────────────────────────────────────
    def build_pg_filter(self, perm: UserPermission) -> tuple[str, list]:
        """반환: (WHERE절 문자열, 파라미터 목록). 파라미터 인덱스는 $1부터 순서대로."""
        clauses: list[str] = []
        params: list = []

        clauses.append("sensitivity = 'public'")

        if perm.teams:
            idx = len(params) + 1
            clauses.append(
                f"(team_id = ANY(${idx}) AND sensitivity = 'internal')"
            )
            params.append(perm.teams)

        if perm.personal_docs:
            idx = len(params) + 1
            clauses.append(
                f"(doc_id = ANY(${idx}) AND sensitivity = 'secret')"
            )
            params.append(perm.personal_docs)

        return " OR ".join(clauses), params

    def _is_accessible(self, src, perm: UserPermission) -> bool:
        if src.sensitivity == "public":
            return True
        if src.sensitivity == "internal":
            return src.team_id in perm.teams
        if src.sensitivity == "secret":
            return src.document_id in perm.personal_docs
        return False

    # ── 캐시 + FGA 연동 (async) ───────────────────────────────
    async def get_permission(self, user_id: str) -> UserPermission:
        cached = await self._cache.get(user_id)
        if cached is not None:
            return cached
        perm = await self._fetch_from_fga(user_id)
        await self._cache.set(user_id, perm, self._config.cache_ttl_seconds)
        return perm

    async def filter_sources(self, sources: list, user_id: str) -> list:
        if not sources:
            return []
        perm = await self.get_permission(user_id)
        return [s for s in sources if self._is_accessible(s, perm)]

    async def _fetch_from_fga(self, user_id: str) -> UserPermission:
        teams = await self._list_fga_objects(f"user:{user_id}", "member", "team")
        personal_docs = await self._query_personal_docs(user_id)
        return UserPermission(user_id=user_id, teams=teams, personal_docs=personal_docs)

    async def _query_personal_docs(self, user_id: str) -> list[str]:
        if self._pg_pool is None:
            return []
        try:
            async with self._pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT doc_id FROM user_doc_grants WHERE user_id = $1", user_id
                )
                return [row["doc_id"] for row in rows]
        except Exception:
            return []

    async def _list_fga_objects(self, user: str, relation: str, type_: str) -> list[str]:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientListObjectsRequest
        from openfga_sdk.exceptions import ValidationException
        cfg = ClientConfiguration(
            api_url=self._config.api_url,
            store_id=self._config.store_id,
        )
        if self._config.api_key:
            from openfga_sdk.credentials import CredentialConfiguration, CredentialMethod
            cfg.credentials = CredentialConfiguration(
                method=CredentialMethod.API_TOKEN,
                configuration=CredentialConfiguration(api_token=self._config.api_key),
            )
        try:
            async with OpenFgaClient(cfg) as client:
                resp = await client.list_objects(
                    ClientListObjectsRequest(user=user, relation=relation, type=type_)
                )
                return resp.objects or []
        except ValidationException as exc:
            if "latest_authorization_model_not_found" in str(exc):
                import logging
                logging.getLogger(__name__).warning(
                    "FGA authorization model not found for store %s — "
                    "run scripts/fga_init.sh to initialize. Returning empty permissions.",
                    self._config.store_id,
                )
                return []
            raise

    async def _write_fga_tuples(self, tuples: list[dict]) -> None:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
        cfg = ClientConfiguration(
            api_url=self._config.api_url,
            store_id=self._config.store_id,
        )
        async with OpenFgaClient(cfg) as client:
            try:
                await client.write(ClientWriteRequest(
                    writes=[ClientTuple(**t) for t in tuples]
                ))
            except Exception as e:
                if not self._is_idempotent_fga_error(e):
                    raise

    @staticmethod
    def _is_idempotent_fga_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "already existed" in msg or "did not exist" in msg

    async def write_tuples(
        self, doc_id: str, owner_id: str, team_id: str, sensitivity: str
    ) -> None:
        fga_obj = f"document:{doc_id.replace(':', '-')}"
        tuples = [{"user": f"user:{owner_id}", "relation": "owner", "object": fga_obj}]
        if sensitivity == "public":
            tuples.append({"user": "user:*", "relation": "viewer", "object": fga_obj})
        elif sensitivity == "internal":
            tuples.append({"user": f"{team_id}#member", "relation": "viewer", "object": fga_obj})
        elif sensitivity == "secret":
            tuples.append({"user": f"user:{owner_id}", "relation": "viewer", "object": fga_obj})
            await self._insert_personal_doc(owner_id, doc_id)
        await self._write_fga_tuples(tuples)
        await self._cache.invalidate(owner_id)

    async def _insert_personal_doc(self, user_id: str, doc_id: str) -> None:
        if self._pg_pool is None:
            return
        async with self._pg_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_doc_grants (
                    user_id TEXT NOT NULL,
                    doc_id  TEXT NOT NULL,
                    PRIMARY KEY (user_id, doc_id)
                )
            """)
            await conn.execute(
                "INSERT INTO user_doc_grants (user_id, doc_id) VALUES ($1, $2) "
                "ON CONFLICT DO NOTHING",
                user_id, doc_id,
            )

    async def _delete_personal_doc(self, user_id: str, doc_id: str) -> None:
        if self._pg_pool is None:
            return
        async with self._pg_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_doc_grants WHERE user_id = $1 AND doc_id = $2",
                user_id, doc_id,
            )

    async def add_team_member(self, user_id: str, team_id: str) -> None:
        await self._write_fga_tuples([
            {"user": f"user:{user_id}", "relation": "member", "object": f"team:{team_id}"}
        ])
        await self._cache.invalidate(user_id)

    async def remove_team_member(self, user_id: str, team_id: str) -> None:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
        cfg = ClientConfiguration(api_url=self._config.api_url, store_id=self._config.store_id)
        async with OpenFgaClient(cfg) as client:
            try:
                await client.write(ClientWriteRequest(
                    deletes=[ClientTuple(
                        user=f"user:{user_id}", relation="member", object=f"team:{team_id}"
                    )]
                ))
            except Exception as e:
                if not self._is_idempotent_fga_error(e):
                    raise
        await self._cache.invalidate(user_id)

    async def grant_doc_access(self, user_id: str, doc_id: str) -> None:
        await self._write_fga_tuples([
            {"user": f"user:{user_id}", "relation": "viewer", "object": f"document:{doc_id}"}
        ])
        await self._insert_personal_doc(user_id, doc_id)
        await self._cache.invalidate(user_id)

    async def revoke_doc_access(self, user_id: str, doc_id: str) -> None:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
        cfg = ClientConfiguration(
            api_url=self._config.api_url,
            store_id=self._config.store_id,
        )
        async with OpenFgaClient(cfg) as client:
            try:
                await client.write(ClientWriteRequest(
                    deletes=[ClientTuple(
                        user=f"user:{user_id}", relation="viewer", object=f"document:{doc_id}"
                    )]
                ))
            except Exception as e:
                if not self._is_idempotent_fga_error(e):
                    raise
        await self._delete_personal_doc(user_id, doc_id)
        await self._cache.invalidate(user_id)

    async def delete_user_tuples(self, user_id: str) -> None:
        docs = await self._list_fga_objects(f"user:{user_id}", "viewer", "document")
        teams = await self._list_fga_objects(f"user:{user_id}", "member", "team")
        tuples_to_delete = (
            [{"user": f"user:{user_id}", "relation": "viewer", "object": d} for d in docs]
            + [{"user": f"user:{user_id}", "relation": "member", "object": t} for t in teams]
        )
        if tuples_to_delete:
            from openfga_sdk import OpenFgaClient, ClientConfiguration
            from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
            cfg = ClientConfiguration(
                api_url=self._config.api_url,
                store_id=self._config.store_id,
            )
            async with OpenFgaClient(cfg) as client:
                try:
                    await client.write(ClientWriteRequest(
                        deletes=[ClientTuple(**t) for t in tuples_to_delete]
                    ))
                except Exception as e:
                    if not self._is_idempotent_fga_error(e):
                        raise
        await self._cache.invalidate(user_id)
