from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel

from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store
from app.graph.builder import answer_question, build_graph

app = FastAPI()


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]


@lru_cache(maxsize=1)
def get_graph():
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    llm = create_llm(config)
    return build_graph(retriever=retriever, llm=llm)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    result = answer_question(get_graph(), req.question)
    return ChatResponse(answer=result.text, sources=result.sources)
