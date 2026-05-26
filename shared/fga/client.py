import asyncio
import concurrent.futures
from shared.fga.base import PermissionCacheBackend
from shared.fga.models import FGAConfig, UserPermission


def _run_async(coro):
    """이벤트 루프 유무와 관계없이 코루틴을 동기적으로 실행."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _is_idempotent_fga_error(exc: Exception) -> bool:
    """이미 존재하는 tuple write / 없는 tuple delete → 무시해도 안전."""
    msg = str(exc).lower()
    return "already existed" in msg or "did not exist" in msg


class FGAClient:
    def __init__(self, config: FGAConfig, cache: PermissionCacheBackend) -> None:
        self._config = config
        self._cache = cache

    # ── 순수 함수 ────────────────────────────────────────────
    def build_chroma_filter(self, perm: UserPermission) -> dict:
        clauses: list[dict] = [{"sensitivity": "public"}]
        if perm.teams:
            clauses.append({
                "$and": [
                    {"team_id": {"$in": perm.teams}},
                    {"sensitivity": "internal"},
                ]
            })
        if perm.personal_docs:
            clauses.append({
                "$and": [
                    {"sensitivity": "secret"},
                    {"document_id": {"$in": perm.personal_docs}},
                ]
            })
        if len(clauses) == 1:
            return clauses[0]
        return {"$or": clauses}

    # ── 캐시 + FGA 연동 ───────────────────────────────────────
    def get_permission(self, user_id: str) -> UserPermission:
        cached = self._cache.get(user_id)
        if cached is not None:
            return cached
        perm = self._fetch_from_fga(user_id)
        self._cache.set(user_id, perm, self._config.cache_ttl_seconds)
        return perm

    def _fetch_from_fga(self, user_id: str) -> UserPermission:
        teams = self._list_fga_objects(f"user:{user_id}", "member", "team")
        personal_docs = self._query_personal_docs(user_id)
        return UserPermission(user_id=user_id, teams=teams, personal_docs=personal_docs)

    def _query_personal_docs(self, user_id: str) -> list[str]:
        """user_doc_grants PG 테이블에서 개인 허용 문서 조회. pg_dsn 미설정 시 빈 목록."""
        if not self._config.pg_dsn:
            return []
        import psycopg2
        try:
            with psycopg2.connect(self._config.pg_dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT doc_id FROM user_doc_grants WHERE user_id = %s", (user_id,)
                )
                return [row[0] for row in cur.fetchall()]
        except psycopg2.errors.UndefinedTable:
            return []

    def _list_fga_objects(self, user: str, relation: str, type_: str) -> list[str]:
        """OpenFGA listObjects 호출. 테스트에서 patch 대상."""
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientListObjectsRequest

        async def _inner():
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
            async with OpenFgaClient(cfg) as client:
                resp = await client.list_objects(
                    ClientListObjectsRequest(user=user, relation=relation, type=type_)
                )
                return resp.objects or []

        return _run_async(_inner())

    def _write_fga_tuples(self, tuples: list[dict]) -> None:
        """OpenFGA write 호출. 테스트에서 patch 대상."""
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple

        async def _inner():
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
                    if not _is_idempotent_fga_error(e):
                        raise

        _run_async(_inner())

    def write_tuples(
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
            self._insert_personal_doc(owner_id, doc_id)
        self._write_fga_tuples(tuples)
        self._cache.invalidate(owner_id)

    def _insert_personal_doc(self, user_id: str, doc_id: str) -> None:
        if not self._config.pg_dsn:
            return
        import psycopg2
        with psycopg2.connect(self._config.pg_dsn) as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_doc_grants (
                    user_id TEXT NOT NULL,
                    doc_id  TEXT NOT NULL,
                    PRIMARY KEY (user_id, doc_id)
                )
            """)
            cur.execute(
                "INSERT INTO user_doc_grants (user_id, doc_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, doc_id),
            )

    def _delete_personal_doc(self, user_id: str, doc_id: str) -> None:
        if not self._config.pg_dsn:
            return
        import psycopg2
        with psycopg2.connect(self._config.pg_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_doc_grants WHERE user_id = %s AND doc_id = %s",
                (user_id, doc_id),
            )

    def add_team_member(self, user_id: str, team_id: str) -> None:
        self._write_fga_tuples([{"user": f"user:{user_id}", "relation": "member", "object": f"team:{team_id}"}])
        self._cache.invalidate(user_id)

    def remove_team_member(self, user_id: str, team_id: str) -> None:
        async def _inner():
            from openfga_sdk import OpenFgaClient, ClientConfiguration
            from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
            cfg = ClientConfiguration(api_url=self._config.api_url, store_id=self._config.store_id)
            async with OpenFgaClient(cfg) as client:
                try:
                    await client.write(ClientWriteRequest(
                        deletes=[ClientTuple(user=f"user:{user_id}", relation="member", object=f"team:{team_id}")]
                    ))
                except Exception as e:
                    if not _is_idempotent_fga_error(e):
                        raise
        _run_async(_inner())
        self._cache.invalidate(user_id)

    def grant_doc_access(self, user_id: str, doc_id: str) -> None:
        self._write_fga_tuples([{"user": f"user:{user_id}", "relation": "viewer", "object": f"document:{doc_id}"}])
        self._insert_personal_doc(user_id, doc_id)
        self._cache.invalidate(user_id)

    def revoke_doc_access(self, user_id: str, doc_id: str) -> None:
        async def _inner():
            from openfga_sdk import OpenFgaClient, ClientConfiguration
            from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
            cfg = ClientConfiguration(
                api_url=self._config.api_url,
                store_id=self._config.store_id,
            )
            async with OpenFgaClient(cfg) as client:
                try:
                    await client.write(ClientWriteRequest(
                        deletes=[ClientTuple(user=f"user:{user_id}", relation="viewer", object=f"document:{doc_id}")]
                    ))
                except Exception as e:
                    if not _is_idempotent_fga_error(e):
                        raise
        _run_async(_inner())
        self._delete_personal_doc(user_id, doc_id)
        self._cache.invalidate(user_id)

    def delete_user_tuples(self, user_id: str) -> None:
        """퇴사 처리 — 해당 유저의 모든 tuple 삭제. 캐시 무효화."""
        docs = self._list_fga_objects(f"user:{user_id}", "viewer", "document")
        teams = self._list_fga_objects(f"user:{user_id}", "member", "team")
        tuples_to_delete = (
            [{"user": f"user:{user_id}", "relation": "viewer", "object": d} for d in docs]
            + [{"user": f"user:{user_id}", "relation": "member", "object": t} for t in teams]
        )
        if tuples_to_delete:
            async def _inner():
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
                        if not _is_idempotent_fga_error(e):
                            raise
            _run_async(_inner())
        self._cache.invalidate(user_id)
