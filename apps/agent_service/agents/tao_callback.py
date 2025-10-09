# apps/agent_service/agents/tao_callback.py
"""
TAO (Think-Action-Observation) Callback Handler

Captures agent thinking steps and tool executions in real-time.
Provides transparency to users by showing what the agent is doing.
"""

from langchain.callbacks.base import BaseCallbackHandler
from typing import Any, Dict, List, Optional
import time


class TAOCallback(BaseCallbackHandler):
    """
    Captures agent thinking steps and tool executions in real-time.
    Stores events that can be displayed to the user for transparency.
    
    This callback intercepts:
    - Tool starts/ends (actions being taken)
    - Tool errors (when something fails)
    - Agent reasoning (when deciding what to do)
    """
    
    def __init__(self, language: str = "es"):
        """
        Args:
            language: 'es' or 'en' for localized messages
        """
        super().__init__()
        self.language = language
        self.events: List[Dict[str, Any]] = []
        self.start_time = time.time()
    
    def _translate(self, es: str, en: str) -> str:
        """Simple translation helper"""
        return es if self.language == "es" else en
    
    def on_tool_start(
        self, 
        serialized: Dict[str, Any], 
        input_str: str, 
        **kwargs
    ) -> None:
        """Called when a tool starts executing"""
        tool_name = serialized.get("name", "unknown")
        
        # Map tool names to user-friendly messages
        tool_messages = {
            "player_lookup": self._translate(
                "🔍 Buscando jugador en la base de datos...",
                "🔍 Searching for player in database..."
            ),
            "similar_players_team_fit_table": self._translate(
                "⚽ Analizando jugadores similares y ajuste al equipo...",
                "⚽ Analyzing similar players and team fit..."
            ),
            "build_scouting_report": self._translate(
                "📄 Generando informe de scouting en PDF...",
                "📄 Generating scouting report in PDF..."
            ),
            "dashboard_inline": self._translate(
                "📊 Creando dashboard interactivo...",
                "📊 Creating interactive dashboard..."
            ),
            "radar_chart": self._translate(
                "📈 Generando gráfico radar...",
                "📈 Generating radar chart..."
            ),
            "pizza_chart": self._translate(
                "🍕 Generando gráfico pizza...",
                "🍕 Generating pizza chart..."
            ),
            "radar_comparison_chart": self._translate(
                "📈 Generando gráfico radar comparativo...",
                "📈 Generating comparative radar chart..."
            ),
            "pizza_comparison_chart": self._translate(
                "🍕 Generando gráfico pizza comparativo...",
                "🍕 Generating comparative pizza chart..."
            ),
            "player_stats": self._translate(
                "📊 Obteniendo estadísticas del jugador...",
                "📊 Fetching player statistics..."
            ),
            "player_stats_table": self._translate(
                "📋 Generando tabla de estadísticas...",
                "📋 Generating statistics table..."
            ),
            "compare_players_stats_table": self._translate(
                "📊 Comparando estadísticas de jugadores...",
                "📊 Comparing player statistics..."
            ),
            "choose_best_candidate": self._translate(
                "🎯 Analizando el mejor candidato...",
                "🎯 Analyzing best candidate..."
            ),
        }
        
        message = tool_messages.get(
            tool_name,
            self._translate(
                f"⚙️ Ejecutando {tool_name}...",
                f"⚙️ Executing {tool_name}..."
            )
        )
        
        self.events.append({
            "type": "tool_start",
            "tool": tool_name,
            "message": message,
            "timestamp": time.time() - self.start_time
        })
    
    def on_tool_end(
        self,
        output: str,
        **kwargs
    ) -> None:
        """Called when a tool finishes executing"""
        success_msg = self._translate(
            "✅ Completado",
            "✅ Completed"
        )
        
        self.events.append({
            "type": "tool_end",
            "message": success_msg,
            "timestamp": time.time() - self.start_time
        })
    
    def on_tool_error(
        self,
        error: Exception,
        **kwargs
    ) -> None:
        """Called when a tool fails"""
        error_msg = self._translate(
            f"❌ Error: {str(error)}",
            f"❌ Error: {str(error)}"
        )
        
        self.events.append({
            "type": "tool_error",
            "message": error_msg,
            "timestamp": time.time() - self.start_time
        })
    
    def on_agent_action(self, action, **kwargs) -> None:
        """Called when agent decides on an action (thinking step)"""
        thought_msg = self._translate(
            "🧠 Analizando qué herramientas usar...",
            "🧠 Analyzing which tools to use..."
        )
        
        self.events.append({
            "type": "thinking",
            "message": thought_msg,
            "timestamp": time.time() - self.start_time
        })
    
    def get_events_html(self) -> str:
        """
        Render events as HTML for display in chat.
        Returns an empty string if no events were captured.
        """
        if not self.events:
            return ""
        
        # Filter out duplicate "thinking" events (can happen with retries)
        filtered_events = []
        last_type = None
        for event in self.events:
            if event["type"] == "thinking" and last_type == "thinking":
                continue  # Skip consecutive thinking events
            filtered_events.append(event)
            last_type = event["type"]
        
        if not filtered_events:
            return ""
        
        html_parts = ['<div class="tao-events">']
        
        for event in filtered_events:
            event_type = event["type"]
            message = event["message"]
            
            # Apply CSS class based on event type
            css_class = {
                "tool_start": "tao-event event-action",
                "tool_end": "tao-event event-success",
                "tool_error": "tao-event event-error",
                "thinking": "tao-event event-thinking"
            }.get(event_type, "tao-event event-default")
            
            html_parts.append(
                f'<div class="{css_class}">'
                f'<span class="event-message">{message}</span>'
                f'</div>'
            )
        
        html_parts.append('</div>')
        return "\n".join(html_parts)
    
    def get_events_markdown(self) -> str:
        """
        Render events as markdown for display in chat.
        Uses blockquote style for better visibility.
        """
        if not self.events:
            return ""
        
        # Filter out duplicate "thinking" events
        filtered_events = []
        last_type = None
        for event in self.events:
            if event["type"] == "thinking" and last_type == "thinking":
                continue  # Skip consecutive thinking events
            filtered_events.append(event)
            last_type = event["type"]
        
        if not filtered_events:
            return ""
        
        lines = []
        lines.append("> **🔄 Proceso del Agente**" if self.language == "es" else "> **🔄 Agent Process**")
        lines.append(">")
        
        for event in filtered_events:
            lines.append(f"> {event['message']}")
        
        lines.append("")
        
        return "\n".join(lines)
    
    def reset(self):
        """Clear all captured events"""
        self.events.clear()
        self.start_time = time.time()

