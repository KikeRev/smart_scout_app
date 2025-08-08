from langchain.memory import ConversationBufferMemory
from langchain.agents import initialize_agent , AgentType
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
        """
        Responde siempre en el idioma del usuario, si te pregunta en español, responde en español.
        Si te pregunta en inglés, responde en inglés.
        Eres un asistente de scouting. Responde siempre con vocabulario técnico de fútbol, como si fueras un scout profesional.
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
        8. Si el usuario pide un gráfico de comparación de dos jugadores, primero llama a `player_stats` para obtener las estadísticas de ambos jugadores.
        9. Después usa `radar_comparison_chart` para generar el gráfico de radar de comparación o pizza_comparison_chart para el gráfico de pizza.
        10. Si el usuario pide un dashboard interactivo, llama a `dashboard_inline` usando el `base_player_id` y la lista de `candidate_ids` los ids de 
        los candidatos los tienes en la salida de `similar_players` en el campo 'id', no te inventes ids.
        11. Devuelve el HTML del dashboard inline para que se muestre en la interfaz.
        12. Si el usuario pide un informe en pdf, deberas generar un informe usando `build_report_pdf` que devolverá una url de descarga del informe en pdf.
        Un ejemplo de uso de esta tool seria:
            input:
                {
                "objective": "Buscar extremo izquierdo sub-23 para rotación inmediata",
                "base_id": 640,
                "candidate_ids": [4858, 6253, ...],
                "chosen_id": 4858,
                "recommendation": "Aqui debes de incluir un informe detallado del jugador seleccionado con al menos dos tres parrafos explicando las virtudes
                                    y defectos del jugadors en 4-5 bullet points, y un parrafo final con la justificación de porque deberíamos de contratar
                                    al jugador y que podría aportar al equipo",
                "pros": ["Precio accesible", "Perfil U-23"],
                "cons": ["Sin experiencia en 1ª división"]
                }
            output → {"file_url": "/media/reports/xxxx.pdf"}
        """
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
        agent=AgentType.OPENAI_FUNCTIONS,
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

