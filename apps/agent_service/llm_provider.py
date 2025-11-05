# apps/agent_service/llm_provider.py
"""
Returns a ready-to-use Chat LLM object (OpenAI or Ollama).

  • If OPENAI_API_KEY exists → uses OpenAI.
  • Otherwise → uses local Ollama/Mistral.

Supports:
  stream      – bool, activate streaming token-by-token.
  callbacks   – list of handlers for streaming/logging process.
  user_id     – user identifier for cost tracking.
  session_id  – session identifier for grouping traces.
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
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """
    Returns LLM with optional Langfuse tracking.
    
    Parameters
    ----------
    stream : bool
        If True the model will return tokens in streaming.
    callbacks : list[BaseCallbackHandler] | None
        Callbacks that will process the tokens (streaming, tracing, logging…).
    user_id : str | None
        User identifier for cost tracking per user.
    session_id : str | None
        Session identifier for grouping related requests.
    """
    # --- Remote OpenAI ---------------------------------------------------- #
    api_key = os.environ["OPENAI_API_KEY"]          # ❶ fail-fast if it doesn't exist

    # --- Langfuse Integration (optional) ---------------------------------- #
    all_callbacks = callbacks or []
    
    # Check if Langfuse is enabled and keys are available
    langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "true").lower() == "true"
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    
    if langfuse_enabled and langfuse_public_key and langfuse_secret_key:
        try:
            from langfuse.langchain import CallbackHandler as LangfuseCallback
            from langfuse import Langfuse
            
            # Initialize Langfuse client to ensure it's available for the callback
            # This ensures the callback can properly send traces
            langfuse_client = Langfuse(
                public_key=langfuse_public_key,
                secret_key=langfuse_secret_key,
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
            
            # Langfuse v3 API - The callback reads credentials from environment variables
            # LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST are read from env vars
            # The CallbackHandler only accepts public_key and update_trace as parameters
            langfuse_handler = LangfuseCallback(
                public_key=langfuse_public_key,
            )
            
            all_callbacks.append(langfuse_handler)
            print(f"✅ Langfuse tracking enabled (user_id={user_id}, session_id={session_id})")
            
        except ImportError as e:
            print(f"⚠️  Langfuse package import failed: {e}")
            print("💡 Make sure langfuse is installed: pip install langfuse")
        except Exception as e:
            print(f"⚠️  Error initializing Langfuse: {e}")
            import traceback
            traceback.print_exc()
    else:
        if not langfuse_enabled:
            print("ℹ️  Langfuse tracking disabled (LANGFUSE_ENABLED=false)")
        else:
            print("ℹ️  Langfuse tracking disabled (missing API keys)")

    return ChatOpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        model_name=os.getenv("OPENAI_MODEL", "gpt-4o"),
        temperature=0.2,
        request_timeout=60,
        streaming=stream,
        callbacks=all_callbacks,
    )
