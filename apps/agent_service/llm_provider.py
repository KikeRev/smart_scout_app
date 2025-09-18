# apps/agent_service/llm_provider.py
"""
Returns a ready-to-use Chat LLM object (OpenAI or Ollama).

  • If OPENAI_API_KEY exists → uses OpenAI.
  • Otherwise → uses local Ollama/Mistral.

Supports:
  stream      – bool, activar streaming token-a-token.
  callbacks   – lista de handlers para proceso de streaming/logging.
"""
from __future__ import annotations

import os
from typing import List, Optional

from langchain.callbacks.base import BaseCallbackHandler
from langchain_openai import ChatOpenAI

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
        If True the model will return tokens in streaming.
    callbacks : list[BaseCallbackHandler] | None
        Callbacks that will process the tokens (streaming, tracing, logging…).
    """
    # --- Remote OpenAI ---------------------------------------------------- #
    api_key = os.environ["OPENAI_API_KEY"]          # ❶ fail-fast if it doesn't exist

    return ChatOpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        model_name=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0.2,
        request_timeout=60,
        streaming=stream,
        callbacks=callbacks,
    )


