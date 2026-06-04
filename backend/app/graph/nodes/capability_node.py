_CAPABILITY_TEXT = """저는 다음과 같은 작업을 도와드릴 수 있습니다.

**사내 문서 검색** — 정책·규정·절차·가이드 등 문서 기반 질문
예: "연차 사용 규정이 어떻게 돼?", "보안 정책 알려줘"

**업무 DB 조회** — 직원·매출 등 테이블 값 조회·집계
예: "영업팀 평균 급여 알려줘", "이번 분기 매출 상위 5개 부서는?"

**권한 관리** — 부서 멤버십·폴더 접근·SQL 실행 권한 부여/회수
예: "alice를 engineering 부서에 추가해줘", "finance 폴더 접근 권한 회수해줘"

궁금한 게 있으면 바로 질문해 주세요!"""


def capability_node(state: dict) -> dict:
    return {"answer": _CAPABILITY_TEXT, "citations": []}
