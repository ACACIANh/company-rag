from shared.retriever.retriever import Retriever
from shared.llm.base import LLMClient
from nodes.router import GraphState

_RAG_PROMPT = """\
다음 문서를 참고하여 질문에 한국어로 답하세요.

문서:
{context}

질문: {question}
답변:"""


def make_rag_node(retriever: Retriever, llm: LLMClient):
    def rag_node(state: GraphState) -> GraphState:
        results = retriever.retrieve(state["question"], top_k=5)
        context = "\n\n".join(r.chunk.text for r in results)
        sources = list({r.chunk.source for r in results})

        prompt = _RAG_PROMPT.format(context=context, question=state["question"])
        answer = llm.complete(prompt)

        return {
            **state,
            "context": results,
            "answer": answer,
            "sources": sources,
            "trace": state.get("trace", [])
            + [{"node": "rag", "chunks_retrieved": len(results)}],
        }
    return rag_node
