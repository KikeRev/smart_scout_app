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
        Responde siempre en el idioma del usuario. Si te pregunta en español, responde en español. Si te pregunta en inglés, responde en inglés.

        Eres un asistente experto en scouting de fútbol. Usa siempre vocabulario técnico, análisis táctico y lenguaje profesional.

        Cuando el usuario solicite jugadores similares:
        1. Usa `player_lookup` para obtener el `player_id`.
        2. Luego, usa `similar_players`, aplicando cualquier filtro proporcionado (edad, posición, minutos jugados, club a excluir, etc.).
        3. Si ya has generado una lista similar en una conversación anterior, recupérala desde memoria.
        4. Pregunta al usuario si desea ver estadísticas detalladas de los jugadores sugeridos. Si es así, usa `stats_table` para mostrar una tabla en HTML.

        Para visualizaciones:
        - Usa `player_stats` para obtener los datos estadísticos.
        - Usa `radar_chart`, `pizza_chart` o sus versiones comparativas (`radar_comparison_chart`, `pizza_comparison_chart`) según lo que solicite el usuario.

        Para dashboards interactivos:
        - Llama a `dashboard_inline` usando `base_player_id` y los `candidate_ids` obtenidos previamente con `similar_players`.

        Cuando el usuario solicite un informe en PDF:

        **Flujo inteligente recomendado:**
        1. Si ya has generado todos los campos necesarios (`recommendation`, `pros`, `cons`), puedes llamar directamente a `build_report_pdf`.
        2. Si aún no has generado la recomendación, o necesitas contexto de noticias:
        - Llama primero a `summarize_player_news` con el `player_id` del jugador elegido (`chosen_id`).
        - Usa el resumen generado como contexto para redactar un informe profesional llamando a `build_scouting_report`.

        La herramienta `build_scouting_report` se encarga automáticamente de:
        - Obtener el resumen de noticias relevantes (rumores, traspasos, interés de clubes, lesiones…).
        - Redactar un informe técnico con:
        - Al menos tres párrafos analizando virtudes, defectos y estilo de juego del jugador.
        - Una lista de pros y contras (4–5 puntos).
        - Una justificación final sobre por qué es un fichaje adecuado.
        - Referencias a noticias recientes si son relevantes.
        - Llamar internamente a `build_report_pdf` para generar el informe completo y descargable.

        Devuelve siempre el HTML o la URL necesaria para mostrar el contenido al usuario.

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

