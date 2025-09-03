# apps/agent_service/agents/factory.py
from __future__ import annotations
from typing import Optional

import langchain
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from apps.agent_service.agents.tools import TOOLS
from apps.agent_service.llm_provider import get_llm
from apps.agent_service.memory import get_history, preload_history
from apps.agent_service.agents.output_parser import ScoutParser

langchain.debug = True
langchain.verbose = True

SYSTEM_TEXT = """

        Eres un asistente experto en scouting de fútbol: usa vocabulario técnico, análisis táctico y lenguaje profesional.
        Si la entrada es un saludo o una petición de presentación (ej. 'preséntate', '¿en qué puedes ayudar?') NO llames a 
        herramientas: responde brevemente (entre 5-10 líneas) explicando tus capacidades.
        Responde siempre en el idioma del usuario. Usa vocabulario técnico y tono profesional.

        Cuando el usuario pida jugadores similares:
        1) Llama a `player_lookup_tool` para obtener el `player_id` del jugador base (por nombre).
        2) Llama a `similar_players_tool` aplicando los filtros que indique (edad máxima, posición, minutos mínimos, 
        club a excluir, etc.).
        3) Si ya generaste una lista en esta conversación, recupérala del historial en lugar de recalcularla.
        4) Pregunta si desea ver estadísticas: si dice que sí, llama a `stats_table_tool` (o `compare_stats_table_tool` 
        si compara 2 jugadores).

        Cuando te pidan jugadores similares o shortlist:
        - NO inventes. Debes usar las herramientas registradas.
        - Si falta un parámetro requerido, PREGUNTA por él en una sola frase.

        Visualizaciones:
        - Usa `radar_chart_tool`, `pizza_chart_tool` o sus comparativas (`radar_comparison_chart_tool`, `pizza_comparison_chart_tool`).

        Dashboards:
        - Llama a `dashboard_inline_tool` pasando `base_player_id` y `candidate_ids` (obtenidos de `similar_players_tool`).

        Informes PDF:
        1) Recupera ids previos de `similar_players_tool` desde el historial (si existen).
        2) Si no, usa `player_lookup_tool` + `similar_players_tool`.
        3) Genera el informe con `build_scouting_report_tool`. Si ya tienes el texto de recomendación, puedes usar 
        `build_report_pdf_tool`.

        Reglas:
        - No repitas la pregunta del usuario. Responde ejecutando la acción adecuada o pidiendo **solo** la información que falte.
        - Si la consulta incluye un jugador (ej. “Rüdiger”), intenta `player_lookup_tool` directamente.
        - Si te piden una lista N, devuelve N elementos con nombre, club, edad y un breve motivo. Ofrece ver tabla/visualización.

        Flujo:
        1) Si nombran a un jugador, llama a `player_lookup_tool` (sin filtrar posición salvo que el usuario lo indique).
        2) Llama a `similar_players_tool` aplicando edad máxima, minutos, exclusiones de club/ligas, tamaño de lista 'k'.
        3) Devuelve la lista con: nombre, club, edad y 1 línea de justificación. Ofrece `stats_table_tool` o visualización (radar/pizza).
        4) Para dashboards, usa `dashboard_inline_tool`.
        5) Para informe PDF, usa `build_scouting_report_tool` (o `build_report_pdf_tool` si ya tienes el texto) con ids obtenidos.
        """

SYSTEM_TEXT_new = (
    "Responde siempre en el idioma del usuario.\n"
    "Eres un asistente experto en scouting de fútbol: usa vocabulario técnico, análisis táctico y lenguaje profesional.\n\n"
    "Cuando se pidan jugadores similares:\n"
    "1) Usa `player_lookup_tool` para obtener `player_id`.\n"
    "2) Usa `similar_players_tool` con filtros del usuario (edad, posición, minutos, exclusiones...).\n"
    "3) Si ya generaste una lista antes, recupérala del historial.\n"
    "4) Ofrece mostrar estadísticas detalladas y tablas (`stats_table_tool`).\n\n"
    "Para visualizaciones: `player_stats_tool` + `radar_chart_tool` / `pizza_chart` (o comparativas).\n"
    "Para dashboards: `dashboard_inline_tool` con `base_player_id` y `candidate_ids`.\n"
    "Para informes PDF: recupera ids previos y genera el flujo de reporte usando las tools disponibles.\n"
)


def _to_messages(input_dict: dict) -> dict:
    """Convierte {'input': <texto>} -> {'messages': [HumanMessage(...)]}."""
    text = input_dict.get("input", "")
    return {"messages": [HumanMessage(content=text)]}


def _content_to_text(content) -> str:
    """Convierte content (str | list[dict] | cualquier cosa) a texto legible."""
    if isinstance(content, str):
        return content
    # OpenAI content blocks: [{"type": "text", "text": "..."} , ...]
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if "text" in c:
                    parts.append(str(c["text"]))
                elif "content" in c:
                    parts.append(str(c["content"]))
                elif "tool_call_id" in c and "name" in c:
                    # tool call, no lo mostramos al usuario
                    continue
            else:
                parts.append(str(c))
        return "\n".join([p for p in parts if p]).strip()
    # Fallback
    return str(content)


def _pick_final_text(state: dict) -> dict:
    """
    Extrae el último mensaje 'de asistente' del estado y lo normaliza a {'output': <str>}.
    Prioriza mensajes con type='ai', pero si no existen, usa el último con contenido textual.
    """
    msgs = state.get("messages", []) or []

    # 1) Busca de atrás hacia delante el primero cuyo .type sea 'ai'
    for m in reversed(msgs):
        try:
            if getattr(m, "type", None) == "ai":
                return {"output": _content_to_text(getattr(m, "content", ""))}
        except Exception:
            continue

    # 2) Si no hay 'ai', usa el último que tenga 'content' no vacío
    for m in reversed(msgs):
        content = getattr(m, "content", None)
        if content:
            return {"output": _content_to_text(content)}

    # 3) Fallback vacío
    return {"output": ""}

def build_agent(
    user_id: str = "anon",
    *,
    session_id: Optional[str] = None,
    messages=None,
    streaming_callback: Optional[BaseCallbackHandler] = None,
):
    """
    Agente REACT preconstruido (LangGraph) + memoria conversacional (RunnableWithMessageHistory).
    """
    def _history_getter(cfg):
        # cfg puede venir como str (session_id), dict o None según cómo te llamen
        if isinstance(cfg, str):
            sid_local = cfg
        elif isinstance(cfg, dict):
            sid_local = (
                cfg.get("configurable", {}).get("session_id")
                or session_id
                or user_id
                or "anon"
            )
        else:
            sid_local = session_id or user_id or "anon"
        return get_history(sid_local)

    # 1) LLM (GPT-5 / gpt-5-mini) vía init_chat_model, con streaming y callbacks
    llm = get_llm(
        stream=True,
        callbacks=[streaming_callback] if streaming_callback else None,
    )

    # 2) Prompt con mensaje de sistema (esta versión de create_react_agent usa `prompt=`)
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_TEXT),
        MessagesPlaceholder("messages"),
    ])

    # 3) Agente con tools
    agent = create_react_agent(
        model=llm,
        tools=TOOLS,
        prompt=prompt,  # <- clave en tu versión de LangGraph
    )

    # 4) Precarga opcional de histórico
    sid = session_id or user_id or "anon"
    if messages:
        preload_history(sid, messages)

    # 5) Adaptador de entrada y memoria (historial en 'messages')
    adapter_in = RunnableLambda(_to_messages)

    with_history = RunnableWithMessageHistory(
        agent,
        lambda cfg: _history_getter(cfg),
        input_messages_key="messages",
        history_messages_key="messages",
    )

    # 6) Extraer texto final + tu parser
    extract_text = RunnableLambda(_pick_final_text)
    parser = ScoutParser()
    postprocess = RunnableLambda(lambda x: {"output": parser.parse(x["output"])})

    # 7) Pipeline final
    runnable = adapter_in | with_history | extract_text | postprocess
    return runnable