from shared.config import load_config
from shared.llm.factory import create_llm
from shared.models import Answer
from shared.retriever.embedding import EmbeddingService
from shared.retriever.retriever import Retriever
from shared.vector_store.factory import create_vector_store

_PROMPT_TEMPLATE = """\
다음 문서를 참고하여 질문에 한국어로 답하세요.

문서:
{context}

질문: {question}
답변:"""


def run(question: str) -> Answer:
    config = load_config()
    embedder = EmbeddingService(config.embedding_model)
    store = create_vector_store(config)
    retriever = Retriever(store, embedder)
    llm = create_llm(config)

    results = retriever.retrieve(question, top_k=5)
    context = "\n\n".join(r.chunk.text for r in results)
    sources = list({r.chunk.source for r in results})

    prompt = _PROMPT_TEMPLATE.format(context=context, question=question)
    text = llm.complete(prompt)

    return Answer(text=text, sources=sources, trace=None)
