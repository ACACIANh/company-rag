from core.fga.base import PermissionCacheBackend
from core.fga.models import FGAConfig


def prune_to_top_folders(paths: list[str]) -> list[str]:
    """상속으로 펼쳐진 폴더 목록에서 상위 노드만 남긴다.

    부모가 목록에 있으면 그 자식 경로는 path prefix로 이미 커버되므로 버린다.
    예: ["/a", "/a/b", "/a/b/c", "/x"] → ["/a", "/x"]
    """
    tops: list[str] = []
    for p in sorted(set(paths)):
        if not any(p.startswith(top + "/") for top in tops):
            tops.append(p)
    return tops


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
    def build_pg_filter(self, allowed_folders: list[str]) -> tuple[str, list]:
        """allowed_folders(추려진 상위 폴더) → path prefix WHERE절. 파라미터는 $1부터 순서대로.

        빈 목록이면 접근 가능 폴더가 없으므로 아무 행도 통과하지 않는 절(FALSE)을 반환한다
        (빈 IN으로 전체가 통과되는 사고 방지).
        path 전용 컬럼(idx_documents_path, text_pattern_ops)을 prefix 매칭한다.
        """
        if not allowed_folders:
            return "FALSE", []

        clauses: list[str] = []
        params: list = []
        for folder in allowed_folders:
            eq_idx = len(params) + 1
            like_idx = eq_idx + 1
            # path = folder  OR  path LIKE folder/%  ('/' 경계로 /engineering 가 /engineeringX 를 안 잡게)
            clauses.append(f"(path = ${eq_idx} OR path LIKE ${like_idx})")
            params.append(folder)
            params.append(folder + "/%")

        return " OR ".join(clauses), params

    # ── 캐시 + FGA 연동 (async) ───────────────────────────────
    async def get_readable_folders(self, user_id: str) -> list[str]:
        """추려진 allowed_folders. 캐시 우선, miss 시 ListObjects→상위노드 추림→캐시."""
        cached = await self._cache.get(user_id)
        if cached is not None:
            return cached
        folders = prune_to_top_folders(await self.list_readable_folders(user_id))
        await self._cache.set(user_id, folders, self._config.cache_ttl_seconds)
        return folders

    async def list_readable_folders(self, user_id: str) -> list[str]:
        """사용자가 can_read 가능한 folder path 목록(추림 전). FGA가 부서 멤버십·트리 상속을 풀어 반환."""
        objects = await self._list_fga_objects(f"user:{user_id}", "can_read", "folder")
        prefix = "folder:"
        return [o[len(prefix):] if o.startswith(prefix) else o for o in objects]

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

    async def add_department_member(self, user_id: str, department_id: str) -> None:
        await self._write_fga_tuples([
            {"user": f"user:{user_id}", "relation": "member", "object": f"department:{department_id}"}
        ])
        await self._cache.invalidate(user_id)

    async def remove_department_member(self, user_id: str, department_id: str) -> None:
        from openfga_sdk import OpenFgaClient, ClientConfiguration
        from openfga_sdk.client.models import ClientWriteRequest, ClientTuple
        cfg = ClientConfiguration(api_url=self._config.api_url, store_id=self._config.store_id)
        async with OpenFgaClient(cfg) as client:
            try:
                await client.write(ClientWriteRequest(
                    deletes=[ClientTuple(
                        user=f"user:{user_id}", relation="member", object=f"department:{department_id}"
                    )]
                ))
            except Exception as e:
                if not self._is_idempotent_fga_error(e):
                    raise
        await self._cache.invalidate(user_id)

    async def delete_user_tuples(self, user_id: str) -> None:
        departments = await self._list_fga_objects(f"user:{user_id}", "member", "department")
        tuples_to_delete = [
            {"user": f"user:{user_id}", "relation": "member", "object": d} for d in departments
        ]
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
