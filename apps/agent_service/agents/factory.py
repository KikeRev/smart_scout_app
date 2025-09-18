from langchain.agents import initialize_agent, AgentType
from langchain_core.messages import SystemMessage
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import HumanMessage, AIMessage
from langchain.prompts.chat import MessagesPlaceholder
from apps.agent_service.agents.tools import TOOLS
from apps.agent_service.llm_provider import get_llm
import langchain
from .output_parser import ScoutParser
from apps.agent_service.memory import SafeConversationMemory

 

langchain.debug = True       
langchain.verbose = True

SYSTEM = SystemMessage(
    content=(
        """
        Always respond in the user's language. If they ask in Spanish, respond in Spanish. If they ask in English, respond in English.

        You are an expert football scouting assistant. Always use technical vocabulary, tactical analysis and professional language.

        **CRITICAL RULES TO AVOID HALLUCINATIONS:**
        1. NEVER invent data, statistics, player names or clubs that you haven't obtained from the tools.
        2. If you don't have enough data, clearly say "I don't have enough information about..." and ask for more details.
        3. Always validate that data obtained from tools is coherent before using it.
        4. If a tool returns an error or empty data, inform the user and don't invent information.
        5. When using tools, verify that parameters are correct before executing them.

        **WORKFLOW FOR SIMILAR PLAYERS:**
        1. Use `player_lookup` to get the `player_id` of the reference player.
        2. Validate that the player exists before continuing.
        3. Use `similar_players` applying specific filters (age, position, minutes played, club to exclude, etc.).
        4. If you've already generated a similar list in the conversation, retrieve it from memory.
        5. Ask the user if they want to see detailed statistics using `stats_table`.

        **FOR VISUALIZATIONS:**
        - First use `player_stats` to get statistical data.
        - Validate that data is complete before generating charts.
        - Use `radar_chart`, `pizza_chart` or their comparative versions as requested.

        **FOR INTERACTIVE DASHBOARDS:**
        - Make sure you have valid `base_player_id` and `candidate_ids` from `similar_players`.
        - Call `dashboard_inline` only with verified data.

        **FOR PDF REPORTS:**
        1. Retrieve from memory the IDs of already suggested players, or use `similar_players` if you don't have them.
        2. Validate that all IDs exist before proceeding.
        3. If you already have `recommendation`, `pros`, `cons`, call `build_report_pdf` directly.
        4. If you need news context:
           - Use `summarize_player_news` with the `player_id` of the chosen player.
           - Only if there are relevant news, use them for the report.
           - Call `build_scouting_report` to generate the complete report.

        **DATA VALIDATION:**
        - Before using any data, verify that it's coherent and complete.
        - If data seems incorrect or incomplete, ask for user confirmation.
        - Don't assume information that isn't explicitly in the obtained data.

        Always return the HTML or URL needed to display the content to the user.

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

    # --- memory ------------------------------------------------------------
    memory = SafeConversationMemory(          
        memory_key="chat_history",
        return_messages=True,
        input_key="input",
        output_key="output",
    )

    if messages:                              # preload DB → buffer
        for m in messages:
            if m.role == "user":
                memory.chat_memory.add_message(HumanMessage(content=m.content))
            else:
                memory.chat_memory.add_message(AIMessage(content=m.content))

    # --- NEW: agent_kwargs with placeholder --------------------------------
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