from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough

_PROMPT = PromptTemplate.from_template(
    """\
다음 문서를 참고하여 질문에 한국어로 답하세요.

문서:
{context}

질문: {question}
답변:"""
)


def _format_docs(docs) -> str:
    return "\n\n".join(d.page_content for d in docs)


def build_chain(retriever_adapter, llm_adapter):
    """LCEL 파이프라인: retriever | prompt | llm | parser"""
    return (
        {"context": retriever_adapter | _format_docs, "question": RunnablePassthrough()}
        | _PROMPT
        | llm_adapter
        | StrOutputParser()
    )
