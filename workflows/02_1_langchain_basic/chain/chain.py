# DEPRECATED: 새 구조(workflows/pipeline/)로 대체됨. 학습 참조용으로 코드 형태만 보존.
# from operator import itemgetter

# from langchain_core.output_parsers import StrOutputParser
# from langchain_core.prompts import PromptTemplate
# from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough

# _PROMPT = PromptTemplate.from_template(
#     """\
# 다음 문서를 참고하여 질문에 한국어로 답하세요.

# 문서:
# {context}

# 질문: {question}
# 답변:"""
# )


# def _format_docs(docs) -> str:
#     return "\n\n".join(d.page_content for d in docs)


# def build_chain(retriever_adapter, llm_adapter):
#     """LCEL 파이프라인: retriever(1회) → prompt | llm | parser + docs 패스스루

#     입력: question (str)
#     출력: {"text": str, "docs": list[Document]}
#     """
#     # 1단계: retriever + question 보존 (retriever 1회 호출)
#     retrieve_step = RunnableParallel(
#         {"docs": retriever_adapter, "question": RunnablePassthrough()}
#     )
#     # 2단계: docs 공유 — text 생성 + docs 패스스루
#     answer_step = RunnableParallel(
#         {
#             "text": (
#                 {
#                     "context": itemgetter("docs") | RunnableLambda(_format_docs),
#                     "question": itemgetter("question"),
#                 }
#                 | _PROMPT
#                 | llm_adapter
#                 | StrOutputParser()
#             ),
#             "docs": itemgetter("docs"),
#         }
#     )
#     return retrieve_step | answer_step
