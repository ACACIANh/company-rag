# 역할 기반 동적 capability 응답 설계

## 목표

"할수 있는게 뭐야?" 질문에 대한 응답을 사용자의 FGA 권한에 따라 동적으로 분기한다.
- 일반사원: 권한 확인(내 권한 조회)만 표시
- 권한 관리자(`allow_grant@capability:admin` 보유): 전체 권한 관리(부여/회수/조회) 표시

## 판별 기준

OpenFGA Check API: `check(user:<user_id>, allow_grant, capability:admin)`
- `True` → 관리자 텍스트
- `False` → 일반사원 텍스트

JWT/roles 기반이 아닌 FGA 실시간 조회를 사용하므로, 권한 변경이 즉시 반영된다.

## 변경 범위

### 1. `app/graph/nodes/capability_node.py`

- `capability_node`를 async factory 패턴으로 전환 (`tool_gate_node`와 동일 패턴)
- `FGAClient` 파라미터 주입
- 정적 텍스트 상수를 `_TEXT_USER`, `_TEXT_ADMIN` 두 개로 분리

```python
async def capability_node(state: dict, *, fga_client: FGAClient) -> dict:
    can_grant = await fga_client.check(
        f"user:{state['user_id']}", "allow_grant", "capability:admin"
    )
    return {"answer": _TEXT_ADMIN if can_grant else _TEXT_USER, "citations": []}
```

텍스트 분기:

| 섹션 | 일반사원 (`_TEXT_USER`) | 관리자 (`_TEXT_ADMIN`) |
|------|----------------------|----------------------|
| 사내 문서 검색 | 동일 | 동일 |
| 업무 DB 조회 | 동일 | 동일 |
| 권한 확인/관리 | **권한 확인** — 내 부서 소속 및 폴더 접근 권한 조회 | **권한 관리** — 부서 멤버십·폴더 접근·SQL 실행 권한 부여/회수/조회 |

### 2. `app/graph/builder.py`

- `capability` 노드 등록 시 `fga_client` 주입 (1줄 변경)

```python
# Before
g.add_node("capability", capability_node)
# After
g.add_node("capability", partial(capability_node, fga_client=fga_client))
```

## 테스트

`tests/test_capability_node.py` 신규 작성 (또는 기존 파일 수정):
- `can_grant=True` mock → `_TEXT_ADMIN` 반환 확인
- `can_grant=False` mock → `_TEXT_USER` 반환 확인
- FGA check 호출 시 올바른 인자 전달 확인 (`user:<id>`, `allow_grant`, `capability:admin`)

## 선택하지 않은 대안

- **permission_node에 user_can_grant 필드 추가**: 모든 요청에서 불필요한 FGA 호출 발생, AgentState 필드 오염
- **프론트엔드 하드코딩**: FGA 실시간 반영 불가, 권한 로직 누출

## 영향 범위

- `AgentState` 변경 없음
- 기존 capability route 흐름 변경 없음 (builder.py 1줄 + capability_node.py 내부만)
- 다른 노드 영향 없음
