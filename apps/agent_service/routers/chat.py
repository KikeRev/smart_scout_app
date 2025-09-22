# apps/agent_service/routers/chat.py
from __future__ import annotations

from typing import Optional, Literal, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from apps.agent_service.agents.factory import build_agent
import anyio
import queue
from langchain.callbacks.base import BaseCallbackHandler

import langchain

langchain.debug = True       
langchain.verbose = True


router = APIRouter(prefix="/chat", tags=["chat"])


# --------------------------------------------------------------------------- #
#  Pydantic Models
# --------------------------------------------------------------------------- #

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id:    Optional[str] = None      # ← optional, in case you send it
    messages:   Optional[List[ChatMessage]] = None


class ChatStreamRequest(ChatRequest):
    """
    Request for streaming response.
    Optional `session_id` field in case you want
    to maintain/build context on your own.
    """
    session_id: Optional[str] = None

class QueueStreamCallback(BaseCallbackHandler):
    """Push tokens into a Queue; the async thread consumes them."""
    def __init__(self):
        self._q: queue.Queue[str | None] = queue.Queue()

    # ---------- LangChain ----------
    def on_llm_new_token(self, token: str, **_):      # noqa: D401
        self._q.put(token)

    def on_llm_end(self, *_, **__):
        self._q.put(None)            # sentinel => end

    # ---------- async iterator ----------
    async def token_iter(self):
        """Compatible with AnyIO 3 (doesn't use get_running_loop)."""
        while True:
            tok = await anyio.to_thread.run_sync(self._q.get)
            if tok is None:
                break
            yield tok

# ------------------------------------------------------------------ #


# --------------------------------------------------------------------------- #
#  Classic endpoint (complete response in a single JSON)
# --------------------------------------------------------------------------- #
@router.post("/", summary="Chat without streaming")
def chat(req: ChatRequest):
    agent = build_agent(
        user_id=req.user_id or "anon",
        messages=req.messages,            # ← history arrives here
    )
    result = agent.invoke({"input": req.message})
    return {"answer": result["output"]}


# --------------------------------------------------------------------------- #
#  Streaming endpoint (Server-Sent Events)
# --------------------------------------------------------------------------- #
@router.post("/stream", summary="Chat with streaming (SSE)")
async def chat_stream(req: ChatRequest):
    callback = QueueStreamCallback()
    agent = build_agent(
        user_id=req.user_id or "anon",
        messages=req.messages,
        streaming_callback=callback,
    )

    # launch LLM in background to avoid blocking
    async with anyio.create_task_group() as tg:
        tg.start_soon(anyio.to_thread.run_sync, agent.invoke, {"input": req.message})

    async def event_generator():
        async for tok in callback.token_iter():
            yield f"data: {tok}\n\n"

    return StreamingResponse(event_generator(),
                             media_type="text/event-stream")



