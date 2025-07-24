from langchain.memory import ConversationBufferMemory
from langchain.agents import initialize_agent
from langchain_core.messages import SystemMessage
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from apps.agent_service.agents.tools import TOOLS
from apps.agent_service.llm_provider import get_llm
from typing import Optional

SYSTEM = SystemMessage(
    content=(
        "Eres un asistente de scouting.\n"
        "Si el usuario pide jugadores similares:\n"
        "  1. Llama primero a `player_lookup` para obtener el `player_id`.\n"
        "  2. Después usa `similar_players` con los filtros que el usuario mencione.\n"
        "Responde en español y muestra las listas como tablas Markdown breves."
    )
)

def build_agent(user_id: str = "anon", *, streaming_callback: Optional[BaseCallbackHandler] = None):
    llm = get_llm(stream=True, callbacks=[streaming_callback] if streaming_callback else None)

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        human_prefix=f"user_{user_id}",
    )

    # Con Ollama/Mistral usamos zero-shot-react-description
    agent = initialize_agent(
        tools=TOOLS,
        llm=llm,
        agent="openai-multi-functions",
        memory=memory,
        system_message=SYSTEM,
        verbose=True,
    )
    return agent

