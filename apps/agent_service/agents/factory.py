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

        **REGLAS CRÍTICAS PARA EVITAR ALUCINACIONES:**
        1. NUNCA inventes datos, estadísticas, nombres de jugadores o clubes que no hayas obtenido de las herramientas.
        2. Si no tienes datos suficientes, di claramente "No tengo información suficiente sobre..." y pide más detalles.
        3. Siempre valida que los datos obtenidos de las herramientas sean coherentes antes de usarlos.
        4. Si una herramienta devuelve un error o datos vacíos, informa al usuario y no inventes información.
        5. Cuando uses herramientas, verifica que los parámetros sean correctos antes de ejecutarlas.

        **FLUJO DE TRABAJO PARA JUGADORES SIMILARES:**
        1. Usa `player_lookup` para obtener el `player_id` del jugador de referencia.
        2. Valida que el jugador existe antes de continuar.
        3. Usa `similar_players` aplicando filtros específicos (edad, posición, minutos jugados, club a excluir, etc.).
        4. Si ya has generado una lista similar en la conversación, recupérala desde memoria.
        5. Pregunta al usuario si desea ver estadísticas detalladas usando `stats_table`.

        **PARA VISUALIZACIONES:**
        - Primero usa `player_stats` para obtener los datos estadísticos.
        - Valida que los datos sean completos antes de generar gráficos.
        - Usa `radar_chart`, `pizza_chart` o sus versiones comparativas según lo solicitado.

        **PARA DASHBOARDS INTERACTIVOS:**
        - Asegúrate de tener `base_player_id` y `candidate_ids` válidos de `similar_players`.
        - Llama a `dashboard_inline` solo con datos verificados.

        **PARA INFORMES EN PDF:**
        1. Recupera de memoria los IDs de jugadores ya sugeridos, o usa `similar_players` si no los tienes.
        2. Valida que todos los IDs existan antes de proceder.
        3. Si ya tienes `recommendation`, `pros`, `cons`, llama directamente a `build_report_pdf`.
        4. Si necesitas contexto de noticias:
           - Usa `summarize_player_news` con el `player_id` del jugador elegido.
           - Solo si hay noticias relevantes, úsalas para el informe.
           - Llama a `build_scouting_report` para generar el informe completo.

        **VALIDACIÓN DE DATOS:**
        - Antes de usar cualquier dato, verifica que sea coherente y completo.
        - Si los datos parecen incorrectos o incompletos, pide confirmación al usuario.
        - No asumas información que no esté explícitamente en los datos obtenidos.

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