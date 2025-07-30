# apps/agent_service/memory.py
# apps/agent_service/memory.py
import json
from langchain.memory import ConversationBufferMemory
from langchain.schema import AIMessage, HumanMessage

class SafeConversationMemory(ConversationBufferMemory):
    """Guarda sólo texto en memoria; evita ValidationError con dicts."""

    def save_context(self, inputs: dict, outputs: dict) -> None:
        # ‑‑ entrada tal cual ‑‑
        inp = inputs.get(self.input_key, inputs)
        self.chat_memory.add_message(HumanMessage(content=str(inp)))

        # ‑‑ salida: si es dict → toma "text"  o serializa a JSON ‑‑
        out = outputs.get(self.output_key, outputs)
        if isinstance(out, dict):
            out = out.get("text") or json.dumps(out, ensure_ascii=False)

        self.chat_memory.add_message(AIMessage(content=str(out)))