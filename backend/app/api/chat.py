import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pgvector.asyncpg import register_vector
from pydantic import BaseModel

from core.auth.base import AuthUser
from core.config import load_config
from app.ingestion.embedder import get_embedder
from core.fga.cache import make_cache_backend
from core.fga.client import FGAClient
from core.fga.models import FGAConfig
from core.llm.factory import create_llm
from core.observability.cost_tracker import init_tracker
from core.observability.sinks.file_sink import FileSink
from core.reranker.factory import create_reranker
from core.retriever import BasicRetriever
from core.session.factory import create_session_store
from core.vector_store.factory import create_vector_store
from core.document_version.postgres_store import PostgresDocumentVersionStore
from core.observability.audit.postgres_sink import PostgresAuditSink
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from app.graph.builder import answer_question, build_graph, stream_answer
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.deps import check_rate_limit, get_current_user
from app.api.sessions import router as sessions_router

init_tracker([FileSink("logs")])


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()

    async def _init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(
        config.postgres_dsn, init=_init_conn, min_size=2, max_size=10
    )

    embedder = get_embedder(config.embedding_model)
    store = create_vector_store(config, pool)
    await store.ensure_table()

    cache_backend = make_cache_backend(config.fga_cache_backend, pool)
    if hasattr(cache_backend, "ensure_table"):
        await cache_backend.ensure_table()

    fga_config = FGAConfig(
        api_url=config.fga_api_url,
        store_id=config.fga_store_id,
        api_key=config.fga_api_key,
        cache_ttl_seconds=config.fga_cache_ttl_seconds,
    )
    fga_client = FGAClient(config=fga_config, cache=cache_backend, pg_pool=pool)

    session_store = create_session_store(config, pool)
    if hasattr(session_store, "ensure_tables"):
        await session_store.ensure_tables()

    await PostgresDocumentVersionStore(pool).ensure_table()

    # 게이트 감사 로그(ADR-0018)는 운영 DB(app)에 둔다 — SQL 도구 대상(business)과 분리.
    audit_sink = PostgresAuditSink(pool)
    await audit_sink.ensure_table()
    # SQL 도구 전용 read-only 제한계정 풀(ADR-0020). 미설정 시 SQL 게이트 비활성.
    sql_pool = await asyncpg.create_pool(config.sql_tool_dsn) if config.sql_tool_dsn else None
    sql_rw_pool = await asyncpg.create_pool(config.sql_tool_rw_dsn) if config.sql_tool_rw_dsn else None

    retriever = BasicRetriever(store=store, embedder=embedder)
    llm = create_llm(config)
    reranker = create_reranker(config)

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[("core.models", "Chunk"), ("core.models", "SearchResult")]
    )
    async with AsyncPostgresSaver.from_conn_string(
        config.postgres_dsn,
        serde=serde,
    ) as checkpointer:
        await checkpointer.setup()
        graph = build_graph(
            retriever=retriever, llm=llm, reranker=reranker, fga_client=fga_client,
            checkpointer=checkpointer, audit_sink=audit_sink, sql_pool=sql_pool,
            sql_rw_pool=sql_rw_pool, app_pool=pool,
        )

        app.state.pool = pool
        app.state.store = store
        app.state.fga_client = fga_client
        app.state.session_store = session_store
        app.state.graph = graph

        yield

        if sql_pool is not None:
            await sql_pool.close()
        if sql_rw_pool is not None:
            await sql_rw_pool.close()
        await pool.close()


app = FastAPI(lifespan=lifespan)

_config = load_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_config.cors_origins,
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


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> ChatResponse:
    session_id = req.session_id or str(uuid.uuid4())
    is_new_session = req.session_id is None
    store = request.app.state.session_store

    if not is_new_session:
        owned = {s.thread_id for s in await store.list_sessions(current_user["user_id"])}
        if session_id not in owned:
            raise HTTPException(status_code=403, detail="Session not found")

    thread_id = f"{current_user['user_id']}:{session_id}"
    config = {"configurable": {"thread_id": thread_id}}

    chat_history_fallback = None
    if not is_new_session:
        try:
            stored = await store.get_messages(session_id)
            chat_history_fallback = [{"role": m.role, "content": m.content} for m in stored]
        except Exception:
            logging.exception("failed to load fallback history for session_id=%s", session_id)

    result = await answer_question(
        request.app.state.graph,
        req.question,
        config=config,
        user_id=current_user["user_id"],
        chat_history_fallback=chat_history_fallback,
    )

    try:
        if is_new_session:
            await store.create_session(session_id, current_user["user_id"], req.question[:20])
        await store.add_message(session_id, "user", req.question, [])
        await store.add_message(session_id, "assistant", result.text, result.sources)
    except Exception:
        logging.exception("session store write failed for session_id=%s", session_id)

    return ChatResponse(answer=result.text, sources=[s.source for s in result.sources], session_id=session_id)


@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_rate_limit),
) -> StreamingResponse:
    session_id = req.session_id or str(uuid.uuid4())
    is_new_session = req.session_id is None
    store = request.app.state.session_store

    if not is_new_session:
        owned = {s.thread_id for s in await store.list_sessions(current_user["user_id"])}
        if session_id not in owned:
            raise HTTPException(status_code=403, detail="Session not found")

    thread_id = f"{current_user['user_id']}:{session_id}"
    config = {"configurable": {"thread_id": thread_id}}

    async def event_generator():
        token_queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            stream_answer(
                graph=request.app.state.graph,
                question=req.question,
                config=config,
                user_id=current_user["user_id"],
                token_queue=token_queue,
                session_store=store,
                session_id=session_id,
                is_new_session=is_new_session,
            )
        )
        try:
            while True:
                event = await token_queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "done":
                    break
        finally:
            task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
