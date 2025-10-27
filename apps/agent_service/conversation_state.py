"""
Conversation State Management for Agent Context
Helps the agent understand what actions are available based on conversation flow
"""

from enum import Enum
from typing import List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)

class ConversationState(Enum):
    """
    Defines the current state of the conversation to help agent routing
    """
    IDLE = "idle"                           # No active context, ready for new search
    SEARCH_COMPLETED = "search_completed"   # Just completed a player search, can do dashboard/report
    DASHBOARD_AVAILABLE = "dashboard_available"  # Dashboard was created, can do report
    REPORT_AVAILABLE = "report_available"   # Report was created, back to idle-like state

class StateManager:
    """
    Manages conversation state transitions and available actions
    """
    
    # Define what actions are available in each state
    STATE_ACTIONS = {
        ConversationState.IDLE: [
            "search_players", 
            "player_lookup", 
            "visualizations", 
            "stats"
        ],
        ConversationState.SEARCH_COMPLETED: [
            "dashboard", 
            "report", 
            "new_search", 
            "visualizations"
        ],
        ConversationState.DASHBOARD_AVAILABLE: [
            "report", 
            "new_search", 
            "visualizations"
        ],
        ConversationState.REPORT_AVAILABLE: [
            "new_search", 
            "visualizations", 
            "dashboard"
        ]
    }

    # State transition rules
    STATE_TRANSITIONS = {
        ConversationState.IDLE: {
            "search_players": ConversationState.SEARCH_COMPLETED,
            "player_lookup": ConversationState.IDLE,  # stays idle
            "visualizations": ConversationState.IDLE,
            "stats": ConversationState.IDLE
        },
        ConversationState.SEARCH_COMPLETED: {
            "dashboard": ConversationState.DASHBOARD_AVAILABLE,
            "report": ConversationState.REPORT_AVAILABLE,
            "new_search": ConversationState.SEARCH_COMPLETED,  # new search
            "visualizations": ConversationState.SEARCH_COMPLETED
        },
        ConversationState.DASHBOARD_AVAILABLE: {
            "report": ConversationState.REPORT_AVAILABLE,
            "new_search": ConversationState.SEARCH_COMPLETED,
            "visualizations": ConversationState.DASHBOARD_AVAILABLE
        },
        ConversationState.REPORT_AVAILABLE: {
            "new_search": ConversationState.SEARCH_COMPLETED,
            "dashboard": ConversationState.DASHBOARD_AVAILABLE,
            "visualizations": ConversationState.REPORT_AVAILABLE
        }
    }

    @classmethod
    def get_available_actions(cls, state: ConversationState) -> List[str]:
        """Get list of available actions for current state"""
        return cls.STATE_ACTIONS.get(state, [])
    
    @classmethod
    def get_next_state(cls, current_state: ConversationState, action: str) -> ConversationState:
        """Get next state based on current state and action taken"""
        transitions = cls.STATE_TRANSITIONS.get(current_state, {})
        return transitions.get(action, current_state)  # stay in same state if no transition defined
    
    @classmethod
    def validate_action(cls, state: ConversationState, requested_action: str) -> bool:
        """Validate if an action is allowed in current state"""
        available_actions = cls.get_available_actions(state)
        return requested_action in available_actions
    
    @classmethod
    def get_state_description(cls, state: ConversationState) -> str:
        """Get human-readable description of what's possible in this state"""
        descriptions = {
            ConversationState.IDLE: "Ready for new player search or analysis",
            ConversationState.SEARCH_COMPLETED: "Player search completed - can create dashboard or PDF report",
            ConversationState.DASHBOARD_AVAILABLE: "Dashboard available - can generate PDF report or new search",
            ConversationState.REPORT_AVAILABLE: "Report created - can start new search or create dashboard"
        }
        return descriptions.get(state, "Unknown state")
    
    @classmethod
    def get_recommended_actions(cls, state: ConversationState) -> List[str]:
        """Get recommended next actions for current state"""
        recommendations = {
            ConversationState.IDLE: ["Ask for similar players search"],
            ConversationState.SEARCH_COMPLETED: ["Create dashboard", "Generate PDF report"],
            ConversationState.DASHBOARD_AVAILABLE: ["Generate PDF report"],
            ConversationState.REPORT_AVAILABLE: ["Start new search"]
        }
        return recommendations.get(state, [])

def add_state_to_context(context: Dict, state: ConversationState, action_taken: Optional[str] = None) -> Dict:
    """
    Add conversation state information to context dictionary
    """
    context["conversation_state"] = state.value
    context["state_description"] = StateManager.get_state_description(state)
    context["available_actions"] = StateManager.get_available_actions(state)
    context["recommended_actions"] = StateManager.get_recommended_actions(state)
    
    if action_taken:
        context["last_action"] = action_taken
        context["next_state"] = StateManager.get_next_state(state, action_taken).value
    
    logger.info(f"Context updated - State: {state.value}, Available actions: {context['available_actions']}")
    return context

def parse_state_from_context(context: Dict) -> ConversationState:
    """
    Parse conversation state from context dictionary
    """
    state_value = context.get("conversation_state", ConversationState.IDLE.value)
    try:
        return ConversationState(state_value)
    except ValueError:
        logger.warning(f"Invalid state value '{state_value}', defaulting to IDLE")
        return ConversationState.IDLE

def update_state_after_action(context: Dict, action: str) -> Dict:
    """
    Update conversation state after an action is taken
    """
    current_state = parse_state_from_context(context)
    next_state = StateManager.get_next_state(current_state, action)
    
    if next_state != current_state:
        logger.info(f"State transition: {current_state.value} -> {next_state.value} (action: {action})")
        context = add_state_to_context(context, next_state, action)
    
    return context
