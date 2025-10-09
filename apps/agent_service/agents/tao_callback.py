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
    
    def __init__(self, language: str = "es", stream_callback=None):
        """
        Args:
            language: 'es' or 'en' for localized messages
            stream_callback: Optional QueueStreamCallback to emit SSE events in real-time
        """
        super().__init__()
        self.language = language
        self.events: List[Dict[str, Any]] = []
        self.start_time = time.time()
        self.stream_callback = stream_callback  # Reference to QueueStreamCallback
        self.event_queue = None  # Optional queue for Django SSE streaming
    
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
        
        # Map tool names to user-friendly messages (ALWAYS IN ENGLISH for consistency)
        tool_messages = {
            "player_lookup": "🔍 Searching for player in database...",
            "similar_players_team_fit_table": "⚽ Analyzing similar players and team fit...",
            "build_scouting_report": "📄 Generating scouting report (PDF)...",
            "dashboard_inline": "📊 Creating interactive dashboard...",
            "radar_chart": "📈 Generating radar chart...",
            "pizza_chart": "🍕 Generating pizza chart...",
            "radar_comparison_chart": "📈 Generating comparative radar chart...",
            "pizza_comparison_chart": "🍕 Generating comparative pizza chart...",
            "player_stats": "📊 Fetching player statistics...",
            "player_stats_table": "📋 Generating statistics table...",
            "compare_players_stats_table": "📊 Comparing player statistics...",
            "choose_best_candidate": "🎯 Analyzing best candidate...",
            "player_news": "📰 Fetching player news...",
        }
        
        message = tool_messages.get(tool_name, f"⚙️ Executing {tool_name}...")
        
        event = {
            "type": "tool_start",
            "tool": tool_name,
            "message": message,
            "timestamp": time.time() - self.start_time
        }
        self.events.append(event)
        
        # Emit to Django queue if available
        print(f"[TAO DEBUG] on_tool_start called, tool={tool_name}, has_queue={self.event_queue is not None}")
        if self.event_queue is not None:
            print(f"[TAO DEBUG] Emitting tool_start: {message}")
            self.event_queue.put({"type": "tao", "message": message})
        
        # Emit to stream if available
        if self.stream_callback and hasattr(self.stream_callback, 'emit_tao'):
            self.stream_callback.emit_tao(message)
    
    def on_tool_end(
        self,
        output: str,
        **kwargs
    ) -> None:
        """Called when a tool finishes executing"""
        success_msg = "✅ Completed"
        
        event = {
            "type": "tool_end",
            "message": success_msg,
            "timestamp": time.time() - self.start_time
        }
        self.events.append(event)
        
        # Emit to Django queue if available
        if self.event_queue is not None:
            self.event_queue.put({"type": "tao", "message": success_msg})
        
        # Emit to stream if available
        if self.stream_callback and hasattr(self.stream_callback, 'emit_tao'):
            self.stream_callback.emit_tao(success_msg)
    
    def on_tool_error(
        self,
        error: Exception,
        **kwargs
    ) -> None:
        """Called when a tool fails"""
        error_msg = f"❌ Error: {str(error)}"
        
        event = {
            "type": "tool_error",
            "message": error_msg,
            "timestamp": time.time() - self.start_time
        }
        self.events.append(event)
        
        # Emit to Django queue if available
        if self.event_queue is not None:
            self.event_queue.put({"type": "tao", "message": error_msg})
        
        # Emit to stream if available
        if self.stream_callback and hasattr(self.stream_callback, 'emit_tao'):
            self.stream_callback.emit_tao(error_msg)
    
    def on_agent_action(self, action, **kwargs) -> None:
        """Called when agent decides on an action (thinking step)"""
        thought_msg = "🧠 Analyzing which tools to use..."
        
        event = {
            "type": "thinking",
            "message": thought_msg,
            "timestamp": time.time() - self.start_time
        }
        self.events.append(event)
        
        # Emit to Django queue if available
        if self.event_queue is not None:
            self.event_queue.put({"type": "tao", "message": thought_msg})
        
        # Emit to stream if available
        if self.stream_callback and hasattr(self.stream_callback, 'emit_tao'):
            self.stream_callback.emit_tao(thought_msg)
    
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

