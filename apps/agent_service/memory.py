# apps/agent_service/memory.py

from __future__ import annotations
from typing import Dict, List, Optional

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

# Almacenamiento simple en memoria del proceso (sustituible por Redis/DB)
_HISTORY: Dict[str, InMemoryChatMessageHistory] = {}


def get_history(session_id: str) -> InMemoryChatMessageHistory:
    """Devuelve (o crea) el historial de chat para una sesión concreta."""
    if session_id not in _HISTORY:
        _HISTORY[session_id] = InMemoryChatMessageHistory()
    return _HISTORY[session_id]


def preload_history(session_id: str, messages: Optional[List[BaseMessage]]):
    """
    Opcional: precarga mensajes previos (si tu router te los pasa).
    Adapta roles 'user'/'assistant' a Human/AI.
    """
    if not messages:
        return
    hist = get_history(session_id)
    for m in messages:
        role = getattr(m, "role", None)
        content = getattr(m, "content", None)
        if not content:
            continue
        if role == "user":
            hist.add_message(HumanMessage(content=content))
        elif role == "assistant":
            hist.add_message(AIMessage(content=content))