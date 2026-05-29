# User Team & Role View — Design Spec

**Date:** 2026-05-26  
**Status:** Approved  
**Scope:** 로그인한 유저의 팀(teams)·역할(roles)을 헤더에 표시

---

## 1. 목표

채팅 페이지 헤더에서 현재 로그인한 유저의 팀과 역할을 즉시 확인할 수 있게 한다.

---

## 2. 아키텍처

### 데이터 흐름

```
users.yaml (teams 필드)
  └─ /auth/token (로그인)
       └─ JWT payload { sub, roles, teams, allowed_doc_ids }
            └─ /auth/me → AuthUser { user_id, roles, teams, allowed_doc_ids }
                 └─ AuthContext.user
                      └─ ChatPage 헤더 배지 렌더링
```

### 결정 사항

- **teams 출처**: `users.yaml` → JWT 인코딩. FGA 실시간 조회 없음.
- **teams 변경 반영**: 관리자가 FGA로 팀 변경 시 재로그인 필요 (프로토타입 수준에서 허용).
- **빈 teams**: `[]`이면 team 배지 미표시.

---

## 3. 백엔드 변경

### 3-1. `shared/auth/base.py`

```python
class AuthUser(TypedDict):
    user_id: str
    roles: list[str]
    teams: list[str]          # 신규
    allowed_doc_ids: list[str]
```

### 3-2. `shared/auth/jwt_handler.py`

`create_token()`에 `teams: list[str]` 파라미터 추가:

```python
def create_token(
    user_id: str,
    roles: list[str],
    teams: list[str],
    allowed_doc_ids: list[str],
    secret: str,
    expire_minutes: int,
) -> str:
    payload = {
        "sub": user_id,
        "roles": roles,
        "teams": teams,
        "allowed_doc_ids": allowed_doc_ids,
        "exp": ...,
    }
```

### 3-3. `app/api/auth.py`

`/auth/token` 핸들러에서 `users.yaml`의 `teams` 필드 읽기 (없으면 `[]`):

```python
token = create_token(
    user_id=user["user_id"],
    roles=user["roles"],
    teams=user.get("teams", []),
    allowed_doc_ids=user["allowed_doc_ids"],
    ...
)
```

### 3-4. `app/api/deps.py`

`get_current_user()`에서 `teams` 추출:

```python
return AuthUser(
    user_id=payload["sub"],
    roles=payload["roles"],
    teams=payload.get("teams", []),
    allowed_doc_ids=payload["allowed_doc_ids"],
)
```

`/auth/me`는 `dict(current_user)` 그대로 반환하므로 자동으로 `teams` 포함.

---

## 4. 프론트엔드 변경

### 4-1. `web/src/types.ts`

```typescript
export interface AuthUser {
  user_id: string;
  roles: string[];
  teams: string[];        // 신규
  allowed_doc_ids: string[];
}
```

### 4-2. `web/src/chat/ChatPage.tsx`

헤더 사용자 영역 교체:

**변경 전:**
```
user-alice                    로그아웃
```

**변경 후:**
```
user-alice    role: [user]    team: [general]    로그아웃
```

- `role:` / `team:` 레이블: `text-[13px] text-ink-mute`
- 배지: `pill-tag-soft` — `bg-primary-bg-subdued-hover text-primary-deep text-[10px] font-[400] tracking-[0.1px] rounded-pill px-2 py-1`
- teams가 비어 있으면 `team:` 섹션 전체 미렌더링

---

## 5. 테스트

### 백엔드

| 대상 | 케이스 |
|------|--------|
| `jwt_handler` | `teams` 포함 토큰 생성/디코딩 단위 테스트 |
| `POST /auth/token` | 응답 JWT 디코딩 시 `teams` 클레임 존재 확인 |
| `GET /auth/me` | `teams` 필드 반환 확인 |
| users.yaml teams 없는 유저 | `teams: []` 반환 확인 |

### 프론트엔드

| 대상 | 케이스 |
|------|--------|
| `AuthContext` | `/auth/me` 모킹에 `teams` 포함 |
| `ChatPage` 헤더 | role/team 배지 렌더링 확인 |
| `ChatPage` 헤더 | teams 빈 배열 시 team 배지 미표시 확인 |

---

## 6. 변경 범위 요약

| 파일 | 변경 유형 |
|------|-----------|
| `shared/auth/base.py` | `teams` 필드 추가 |
| `shared/auth/jwt_handler.py` | `teams` 파라미터 추가 |
| `app/api/auth.py` | `users.yaml`에서 `teams` 읽어 전달 |
| `app/api/deps.py` | JWT에서 `teams` 추출 |
| `web/src/types.ts` | `AuthUser.teams` 추가 |
| `web/src/chat/ChatPage.tsx` | 헤더 배지 렌더링 |
| 테스트 파일 (백/프론트) | 신규 케이스 추가 |
