# apps/agent_service/routers/chat.py
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Dict, Optional, Literal, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain.callbacks.base import AsyncCallbackHandler
from pydantic import BaseModel, Field
from apps.agent_service.agents.factory import build_agent
import anyio
import queue
from starlette.responses import StreamingResponse
from langchain.callbacks.base import BaseCallbackHandler

import langchain

langchain.debug = True       
langchain.verbose = True


router = APIRouter(prefix="/chat", tags=["chat"])


# --------------------------------------------------------------------------- #
#  Modelos Pydantic
# --------------------------------------------------------------------------- #

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id:    Optional[str] = None      # ← opcional, por si lo mandas
    messages:   Optional[List[ChatMessage]] = None


class ChatStreamRequest(ChatRequest):
    """
    Petición para respuesta en stream.
    Campo opcional `session_id` por si quieres
    mantener/construir contexto por tu cuenta.
    """
    session_id: Optional[str] = None

class QueueStreamCallback(BaseCallbackHandler):
    """Push tokens en una Queue; el hilo async los consume."""
    def __init__(self):
        self._q: queue.Queue[str | None] = queue.Queue()

    # ---------- LangChain ----------
    def on_llm_new_token(self, token: str, **_):      # noqa: D401
        self._q.put(token)

    def on_llm_end(self, *_, **__):
        self._q.put(None)            # centinela => fin

    # ---------- iterador asíncrono ----------
    async def token_iter(self):
        """Compatible con AnyIO 3 (no usa get_running_loop)."""
        while True:
            tok = await anyio.to_thread.run_sync(self._q.get)
            if tok is None:
                break
            yield tok

# ------------------------------------------------------------------ #


# --------------------------------------------------------------------------- #
#  End-point clásico (respuesta completa en un único JSON)
# --------------------------------------------------------------------------- #
@router.post("/", summary="Chat sin streaming")
def chat(req: ChatRequest):
    agent = build_agent(
        user_id=req.user_id or "anon",
        messages=req.messages,            # ← histórico llega aquí
    )
    result = agent.invoke({"input": req.message})
    return {"answer": result["output"]}


# --------------------------------------------------------------------------- #
#  End-point en streaming  (Server-Sent Events)
# --------------------------------------------------------------------------- #
@router.post("/stream", summary="Chat con streaming (SSE)")
async def chat_stream(req: ChatRequest):
    callback = QueueStreamCallback()
    agent = build_agent(
        user_id=req.user_id or "anon",
        messages=req.messages,
        streaming_callback=callback,
    )

    # lanza el LLM en segundo plano para no bloquear
    async with anyio.create_task_group() as tg:
        tg.start_soon(anyio.to_thread.run_sync, agent.invoke, {"input": req.message})

    async def event_generator():
        async for tok in callback.token_iter():
            yield f"data: {tok}\n\n"

    return StreamingResponse(event_generator(),
                             media_type="text/event-stream")



