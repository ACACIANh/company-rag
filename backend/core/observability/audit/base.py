"""게이트 감사 로그 인터페이스 (ADR-0018).

신원×위험도 게이트(ADR-0016)의 결정과 SQL 실행 결과를 append-only로 남긴다.
"같은 질문, 다른 결과"를 사후 재구성할 수 있어야 게이트의 신뢰성을 입증할 수 있다.
cost_tracker의 CostSink와 같은 sink 패턴을 따르되 별개 테이블이다.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AuditRecord:
    user_id: str
    department: str        # 신원 스냅샷
    role: str              # 신원 스냅샷
    question: str          # 원본 질문
    generated_sql: str
    sql_risk: str          # ADR-0017 등급
    gate_decision: str     # ALLOW / DENY / JUSTIFY_AND_APPROVE (ADR-0016, 0027)
    reason: str            # 결정 사유(매칭 셀) 또는 본인 기재 실행 사유(ADR-0027)
    result_summary: str    # 실행 결과 요약 또는 거부 대안
    thread_id: str         # checkpoint/thread id


class AuditSink(ABC):
    @abstractmethod
    async def record(self, record: AuditRecord) -> None: ...

    @abstractmethod
    async def count_by_decision(self) -> dict[str, int]:
        """gate_decision 값별 누적 건수. 예: {"ALLOW": 15, "DENY": 3}."""
        ...
