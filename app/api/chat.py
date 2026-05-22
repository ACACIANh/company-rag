import uuid
from functools import lru_cache

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from shared.auth.base import AuthUser
from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.observability.cost_tracker import init_tracker
from shared.observability.sinks.file_sink import FileSink
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store
from app.graph.builder import answer_question, build_graph
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.deps import check_rate_limit, get_current_user

init_tracker([FileSink("logs")])

app = FastAPI()
app.include_router(auth_router)
app.include_router(admin_router)


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str


@lru_cache(maxsize=1)
def get_graph():
    config = load_config()
    embedder = SentenceTransformerEmbedder(config.embedding_model)
    store = create_vector_store(config)
    retriever = BasicRetriever(store=store, embedder=embedder)
    llm = create_llm(config)
    return build_graph(retriever=retriever, llm=llm)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> ChatResponse:
    thread_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = answer_question(
        get_graph(),
        req.question,
        config=config,
        user_id=current_user["user_id"],
        allowed_doc_ids=current_user["allowed_doc_ids"],
    )
    return ChatResponse(answer=result.text, sources=result.sources, session_id=thread_id)
