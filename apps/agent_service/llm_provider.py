# apps/agent_service/llm_provider.py
# apps/agent_service/llm_provider.py
"""
Devuelve un ChatModel listo para usar (OpenAI vía init_chat_model).

  • Requiere OPENAI_API_KEY → usa OpenAI.
  • Soporta streaming token-a-token y callbacks.
"""
from __future__ import annotations

import os
from typing import List, Optional

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler

import langchain

langchain.debug = True
langchain.verbose = True


def get_llm(
    *,
    stream: bool = False,
    callbacks: Optional[List[BaseCallbackHandler]] = None,
):
    """
    Parameters
    ----------
    stream : bool
        Si True el modelo devolverá tokens en streaming.
    callbacks : list[BaseCallbackHandler] | None
        Callbacks que procesarán los tokens (streaming, tracing, logging…).
    """
    # --- OpenAI remoto ---------------------------------------------------- #
    api_key = os.environ["OPENAI_API_KEY"]  # fail-fast si falta

    # Usa OPENAI_MODEL si está definido; por defecto gpt-5
    model = os.getenv("OPENAI_MODEL", "gpt-5")

    # init_chat_model crea un ChatModel 'agnóstico' de proveedor
    llm = init_chat_model(
        model=model,                          # p.ej. "gpt-5" o "gpt-5-mini"
        model_provider="openai",
        api_key=api_key,
        base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
        streaming=stream,
        callbacks=callbacks,
        # Nota: evitamos pasar params no estándar (timeout/max_tokens) para máxima compatibilidad 1.x
        # Fuerza al modelo a elegir alguna tool cuando lo requieras:
        tool_choice=os.getenv("OPENAI_TOOL_CHOICE", "auto"),  # 'auto' | 'required'
    )

    return llm



