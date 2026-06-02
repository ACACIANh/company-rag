from core.fga.base import PermissionCacheBackend
from core.fga.models import FGAConfig


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
        """allowed_folders(ListObjects가 상속까지 푼 가시 폴더 목록) → path 정확 매칭 WHERE절.

        빈 목록이면 접근 가능 폴더가 없으므로 아무 행도 통과하지 않는 절(FALSE)을 반환한다
        (빈 IN으로 전체가 통과되는 사고 방지).

        path-prefix(LIKE) 확장은 하지 않는다: 새 권한 모델은 private_flag로 하위 폴더를
        선택적으로 차단할 수 있어 상위 가시성이 하위 가시성을 함의하지 않는다. 각 청크 path가
        가시 폴더 목록에 정확히 포함될 때만 통과시킨다. (path 컬럼 인덱스로 ANY 매칭)
        """
        if not allowed_folders:
            return "FALSE", []
        return "path = ANY($1)", [allowed_folders]

    # ── 캐시 + FGA 연동 (async) ───────────────────────────────
    async def get_readable_folders(self, user_id: str) -> list[str]:
        """가시 폴더 목록(ListObjects가 상속까지 푼 그대로). 캐시 우선, miss 시 조회→캐시.

        prune하지 않는다: 정확 매칭 pre-filter(build_pg_filter)가 각 폴더를 개별로 쓰므로,
        상위로 합치면 private 하위가 prefix로 새어버린다.
        """
        cached = await self._cache.get(user_id)
        if cached is not None:
            return cached
        folders = await self.list_readable_folders(user_id)
        await self._cache.set(user_id, folders, self._config.cache_ttl_seconds)
        return folders

    async def list_readable_folders(self, user_id: str) -> list[str]:
        """사용자가 can_read 가능한 folder path 목록(추림 전). FGA가 부서 멤버십·트리 상속을 풀어 반환."""
        objects = await self._list_fga_objects(f"user:{user_id}", "can_read", "folder")
        prefix = "folder:"
        return [o[len(prefix):] if o.startswith(prefix) else o for o in objects]

    async def user_roles(self, user_id: str) -> list[str]:
        """user가 member인 role id 목록 (신원 등급 판정용 — ADR-0016). prefix 제거."""
        objects = await self._list_fga_objects(f"user:{user_id}", "member", "role")
        prefix = "role:"
        return [o[len(prefix):] if o.startswith(prefix) else o for o in objects]

    async def user_departments(self, user_id: str) -> list[str]:
        """user가 member인 department id 목록 (신원 등급 판정용 — ADR-0016). prefix 제거."""
        objects = await self._list_fga_objects(f"user:{user_id}", "member", "department")
        prefix = "department:"
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
