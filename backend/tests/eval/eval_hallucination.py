"""환각 검사 회귀 측정 (실제 LLM).

사용법:
    .venv/bin/python -m tests.eval.eval_hallucination

.env의 LLM_PROVIDER / LLM_MODEL / API 키를 사용한다.
근거 있는 종합·의역 답변은 통과(YES), 문서에 없는 날조는 차단(NO)되어야 한다.
"""
from core.config import load_config
from core.llm.factory import create_llm
from core.models import Chunk, SearchResult
from app.graph.nodes.check_hallucination import check_hallucination_node


def _docs(*texts: str) -> list[SearchResult]:
    return [
        SearchResult(chunk=Chunk(text=t, source="doc.md", chunk_id=f"c{i}"), score=0.9)
        for i, t in enumerate(texts)
    ]


CASES = [
    {
        "name": "종합·의역 답변 (통과 기대: YES)",
        "documents": _docs(
            "배포는 스테이징 환경에서 검증을 거친 뒤 프로덕션에 반영한다.",
            "장애 발생 시 직전 버전 태그로 롤백한다.",
        ),
        "answer": (
            "배포 절차는 먼저 스테이징에서 충분히 검증한 뒤 프로덕션에 반영하며, "
            "문제가 생기면 직전 버전 태그로 신속히 롤백합니다."
        ),
        "expect_passed": True,
    },
    {
        "name": "날조 수치·고유명사 (차단 기대: NO)",
        "documents": _docs("배포는 스테이징 검증을 거친 뒤 프로덕션에 반영한다."),
        "answer": "배포는 매주 화요일 오전 3시에 자동 진행되며 최종 승인자는 CTO 김철수입니다.",
        "expect_passed": False,
    },
]


def main() -> None:
    llm = create_llm(load_config())
    ok = 0
    print("=== 환각 판정 회귀 측정 ===")
    for c in CASES:
        state = {"answer": c["answer"], "documents": c["documents"], "retry_count": 0}
        result = check_hallucination_node(state, llm=llm)
        passed = result["hallucination_passed"]
        hit = passed == c["expect_passed"]
        ok += hit
        print(f"{'✅' if hit else '❌'} {c['name']}: passed={passed} (기대={c['expect_passed']})")
    print(f"\n{ok}/{len(CASES)} 통과")


if __name__ == "__main__":
    main()
