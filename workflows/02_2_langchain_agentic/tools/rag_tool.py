# DEPRECATED: 새 구조(workflows/pipeline/)로 대체됨. 학습 참조용으로 코드 형태만 보존.
# from langchain_core.tools import tool
# from shared.models import SearchResult


# def make_rag_tool(retriever):
#     """Retriever를 LangChain @tool로 래핑한다."""

#     @tool
#     def search_company_docs(query: str) -> str:
#         """회사 내부 문서에서 정보를 검색합니다. 회사 정책, 규정, 가이드라인 질문에 사용하세요."""
#         results: list[SearchResult] = retriever.retrieve(query, top_k=5)
#         if not results:
#             return "관련 문서를 찾을 수 없습니다."
#         return "\n\n".join(
#             f"[{r.chunk.source}] {r.chunk.text}" for r in results
#         )

#     return search_company_docs
