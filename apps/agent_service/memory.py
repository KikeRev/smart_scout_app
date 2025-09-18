# apps/agent_service/memory.py
import json
from langchain.memory import ConversationBufferMemory
from langchain.schema import AIMessage, HumanMessage

class SafeConversationMemory(ConversationBufferMemory):
    """Saves only text in memory; avoids ValidationError with dicts."""

    def save_context(self, inputs: dict, outputs: dict) -> None:
        # -- input as is --
        inp = inputs.get(self.input_key, inputs)
        self.chat_memory.add_message(HumanMessage(content=str(inp)))

        # -- output: if dict → take "text" or serialize to JSON --
        out = outputs.get(self.output_key, outputs)
        if isinstance(out, dict):
            out = out.get("text") or json.dumps(out, ensure_ascii=False)

        self.chat_memory.add_message(AIMessage(content=str(out)))