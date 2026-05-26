import logging
import uuid
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.auth.base import AuthUser
from shared.config import load_config
from shared.embedder import SentenceTransformerEmbedder
from shared.llm.factory import create_llm
from shared.observability.cost_tracker import init_tracker
from shared.observability.sinks.file_sink import FileSink
from shared.reranker.factory import create_reranker
from shared.retriever import BasicRetriever
from shared.vector_store.factory import create_vector_store
from app.graph.builder import answer_question, build_graph
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.deps import check_rate_limit, get_current_user, get_session_store
from app.api.sessions import router as sessions_router

init_tracker([FileSink("logs")])

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=load_config().cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(sessions_router)


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
    reranker = create_reranker(config)
    return build_graph(retriever=retriever, llm=llm, reranker=reranker)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> ChatResponse:
    session_id = req.session_id or str(uuid.uuid4())
    is_new_session = req.session_id is None
    store = get_session_store()

    if not is_new_session:
        owned = {s.thread_id for s in store.list_sessions(current_user["user_id"])}
        if session_id not in owned:
            raise HTTPException(status_code=403, detail="Session not found")

    thread_id = f"{current_user['user_id']}:{session_id}"
    config = {"configurable": {"thread_id": thread_id}}
    result = answer_question(
        get_graph(),
        req.question,
        config=config,
        user_id=current_user["user_id"],
        allowed_doc_ids=current_user["allowed_doc_ids"],
    )

    try:
        if is_new_session:
            store.create_session(session_id, current_user["user_id"], req.question[:20])
        store.add_message(session_id, "user", req.question, [])
        store.add_message(session_id, "assistant", result.text, result.sources)
    except Exception:
        logging.exception("session store write failed for session_id=%s", session_id)

    return ChatResponse(answer=result.text, sources=[s.source for s in result.sources], session_id=session_id)
