# apps/agent_service/routers/chat.py
from __future__ import annotations

from typing import AsyncIterator, Dict, Optional, Literal, List
import queue

import anyio
from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from langchain_core.callbacks import BaseCallbackHandler

from apps.agent_service.agents.factory import build_agent

import langchain
langchain.debug = True
langchain.verbose = True

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    messages: Optional[List[ChatMessage]] = None


class QueueStreamCallback(BaseCallbackHandler):
    """Callback simple que empuja tokens a una cola para SSE."""
    def __init__(self):
        self._q: "queue.Queue[str | None]" = queue.Queue()

    def on_llm_new_token(self, token: str, **_):
        self._q.put(token)

    def on_llm_end(self, *_, **__):
        self._q.put(None)

    async def token_iter(self):
        while True:
            tok = await anyio.to_thread.run_sync(self._q.get)
            if tok is None:
                break
            yield tok


@router.post("/", summary="Chat sin streaming")
def chat(req: ChatRequest):
    sid = req.session_id or req.user_id or "anon"

    agent = build_agent(
        user_id=req.user_id or "anon",
        session_id=sid,          # precarga opcional en factory
        messages=req.messages,
    )

    result = agent.invoke(
        {"input": req.message},
        {"configurable": {"session_id": sid}},   # clave para la memoria 1.x
    )
    # agent | RunnableLambda devuelve {"output": "..."} para mantener tu contrato
    return {"answer": result["output"]}


@router.post("/stream", summary="Chat con streaming (SSE)")
async def chat_stream(req: ChatRequest):
    sid = req.session_id or req.user_id or "anon"
    callback = QueueStreamCallback()

    agent = build_agent(
        user_id=req.user_id or "anon",
        session_id=sid,
        messages=req.messages,
        streaming_callback=callback,
    )

    async def event_generator():
        # Ejecutamos la invocación en un hilo y streameamos tokens según llegan
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                anyio.to_thread.run_sync,
                agent.invoke,
                {"input": req.message},
                {"configurable": {"session_id": sid}},
            )
            async for tok in callback.token_iter():
                yield f"data: {tok}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")





