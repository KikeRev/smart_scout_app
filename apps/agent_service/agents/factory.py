from langchain.memory import ConversationBufferMemory
from langchain.agents import initialize_agent
from langchain_core.messages import SystemMessage
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.prompts.chat import MessagesPlaceholder
from apps.agent_service.agents.tools import TOOLS
from apps.agent_service.llm_provider import get_llm
from typing import Optional

import langchain

langchain.debug = True       
langchain.verbose = True

SYSTEM = SystemMessage(
    content=(
        "Eres un asistente de scouting.\n"
        "Si el usuario pide jugadores similares:\n"
        "  1. Llama primero a `player_lookup` para obtener el `player_id`.\n"
        "  2. Después usa `similar_players` con los filtros que el usuario mencione.\n"
        "  3. En memoria tienes las respuestas pasadas para poder consultar tus respuestas anteriores.\n" \
        "     por si el usuario pregunta por un jugador que ya has respondido o por listas que ya has creado.\n"
        "  4. Puedes preguntar al usuario si quiere ver algunas estadísticas concretas de la lista que has .\n"
        "     propocionado, en ese caso puedes consultar las estadísticas de los jugadores en la base de datos.\n"
        "     y devolverlas en forma de dataframe de pandas y mostrarlo en pantalla, si no te dice estadisticas.\n"
        "     concretas, muestra las estadísticas más relevantes en base a la posición de los jugadores.\n"
        "Responde en español y muestra las listas como pandas dataframes."
    )
)



def build_agent(
    user_id: str = "anon",
    *,
    messages=None,
    streaming_callback: BaseCallbackHandler | None = None,
):
    llm = get_llm(
        stream=True,
        callbacks=[streaming_callback] if streaming_callback else None,
    )

    # --- memoria ------------------------------------------------------------
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
    )

    if messages:                              # precarga BD → buffer
        for m in messages:
            if m.role == "user":
                memory.chat_memory.add_message(HumanMessage(content=m.content))
            else:
                memory.chat_memory.add_message(AIMessage(content=m.content))

    # --- NUEVO: agent_kwargs con placeholder --------------------------------
    agent = initialize_agent(
        tools=TOOLS,
        llm=llm,
        agent="openai-multi-functions",
        memory=memory,
        agent_kwargs={
            "system_message": SYSTEM,
            "extra_prompt_messages": [
                MessagesPlaceholder(variable_name="chat_history")
            ],
        },
        verbose=True,
    )
    return agent

