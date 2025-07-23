# apps/agent_service/llm_provider.py
"""
Devuelve un objeto Chat LLM (OpenAI u Ollama) listo para usar.

  • Si existe OPENAI_API_KEY → usa OpenAI.
  • En caso contrario → usa Ollama/Mistral local.

Admite:
  stream      – bool, activar streaming token-a-token.
  callbacks   – lista de handlers para proceso de streaming/logging.
"""
from __future__ import annotations

import os
from typing import List, Optional

from langchain.callbacks.base import BaseCallbackHandler
from langchain_community.chat_models import ChatOllama
from langchain_openai import ChatOpenAI


def get_llm(
    *,
    stream: bool = False,
    callbacks: Optional[List[BaseCallbackHandler]] = None,
):
    """
    Parameters
    ----------
    stream : bool
        Si True el modelo devolverá los tokens en streaming.
    callbacks : list[BaseCallbackHandler] | None
        Callbacks que procesarán los tokens (streaming, tracing, logging…).
    """
    # --- OpenAI remoto ---------------------------------------------------- #
    if os.getenv("OPENAI_API_KEY"):
        return ChatOpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
            model_name=os.getenv("OPENAI_MODEL", "gpt-4o"),
            temperature=0.2,
            request_timeout=60,
            streaming=stream,
            callbacks=callbacks,
        )

    # --- Ollama / Mistral local ------------------------------------------ #
    return ChatOllama(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://llm:11434"),
        model=os.getenv("OLLAMA_MODEL", "mistral"),
        temperature=0.2,
        timeout=60,
        streaming=stream,          # ChatOllama también soporta streaming
        callbacks=callbacks,
    )


