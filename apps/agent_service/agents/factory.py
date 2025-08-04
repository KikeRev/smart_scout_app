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
from .output_parser import ScoutParser
from apps.agent_service.memory import SafeConversationMemory

 

langchain.debug = True       
langchain.verbose = True

SYSTEM = SystemMessage(
    content=(
        """Eres un asistente de scouting.
        Si el usuario pide jugadores similares:
          1. Llama primero a `player_lookup` para obtener el `player_id`.
          2. Después usa `similar_players` con los filtros que el usuario mencione.
          3. En memoria tienes las respuestas pasadas para poder consultar tus respuestas anteriores.
             por si el usuario pregunta por un jugador que ya has respondido o por listas que ya has creado.
          4. Puedes preguntar al usuario si quiere ver algunas estadísticas concretas de la lista que has .
             propocionado, en ese caso puedes consultar las estadísticas de los jugadores en la base de datos.
             y devolverlas usa la tool`stats_table` para obtenerla en formato HTML.
        
          5. Si el usuario pide un gráfico de radar, primero llama a `player_stats` para obtener las estadísticas del jugador.
          6. Después usa `radar_chart` para generar el gráfico de radar con las estadísticas del jugador.
          7. Si el usuario pide un gráfico de pizza, primero llama a `player_stats` para obtener las estadísticas del jugador.
             Después usa `pizza_chart` para generar el gráfico de pizza con las estadísticas del jugador.
        """
        "Puedes responder en español o en inglés, dependiendo de como te pregunte el usuario, trata de responder en el mismo idioma."
        "Responde siempre con vocabulario técnico de fútbol, como si fueras un scout profesional."
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
    memory = SafeConversationMemory(          
        memory_key="chat_history",
        return_messages=True,
        input_key="input",
        output_key="output",
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
        output_parser = ScoutParser(), 
        verbose=True,
    )
    return agent

