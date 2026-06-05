from core.fga.client import FGAClient
from core.observability.audit.base import AuditSink

_TEXT_USER = """저는 다음과 같은 작업을 도와드릴 수 있습니다.

**사내 문서 검색** — 정책·규정·절차·가이드 등 문서 기반 질문
예: "연차 사용 규정이 어떻게 돼?", "보안 정책 알려줘"

**업무 DB 조회** — 직원·매출 등 테이블 값 조회·집계
예: "영업 평균 급여 알려줘", "이번 분기 매출 상위 5개 부서는?"

**권한 확인** — 내 부서 소속 및 폴더 접근 권한 조회
예: "내 권한 알려줘", "나 어느 부서에 속해 있어?"

궁금한 게 있으면 바로 질문해 주세요!"""

_TEXT_ADMIN = """저는 다음과 같은 작업을 도와드릴 수 있습니다.

**사내 문서 검색** — 정책·규정·절차·가이드 등 문서 기반 질문
예: "연차 사용 규정이 어떻게 돼?", "보안 정책 알려줘"

**업무 DB 조회** — 직원·매출 등 테이블 값 조회·집계
예: "영업 평균 급여 알려줘", "이번 분기 매출 상위 5개 부서는?"

**권한 관리** — 부서 멤버십·폴더 접근·SQL 실행 권한 부여/회수/조회
예: "노주환를 개발에 추가해줘", "내 권한 알려줘", "finance 폴더 접근 권한 회수해줘"

궁금한 게 있으면 바로 질문해 주세요!"""


# 감사 요약: gate_decision 키 → 표시 라벨 (JUSTIFY_AND_APPROVE는 JUSTIFY로 축약)
_DECISION_LABELS: tuple[tuple[str, str], ...] = (
    ("ALLOW", "ALLOW"),
    ("DENY", "DENY"),
    ("JUSTIFY_AND_APPROVE", "JUSTIFY"),
)


def _format_audit_summary(counts: dict[str, int]) -> str:
    total = sum(counts.get(key, 0) for key, _ in _DECISION_LABELS)
    parts = " · ".join(f"{label} {counts.get(key, 0)}" for key, label in _DECISION_LABELS)
    return f"\n\n📊 최근 게이트 결정: 총 {total}건 ({parts})"


async def capability_node(state: dict, *, fga_client: FGAClient, audit_sink: AuditSink | None = None) -> dict:
    can_grant = await fga_client.check(
        f"user:{state['user_id']}", "justify_grant", "capability:admin"
    )
    if not can_grant:
        return {"answer": _TEXT_USER, "citations": []}
    answer = _TEXT_ADMIN
    if audit_sink is not None:
        counts = await audit_sink.count_by_decision()
        answer += _format_audit_summary(counts)
    return {"answer": answer, "citations": []}
