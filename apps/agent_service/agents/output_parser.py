# apps/agent_service/agents/output_parser.py
from langchain_core.output_parsers import BaseOutputParser

class ScoutParser(BaseOutputParser):
    """Convierte la salida de la tool en un mensaje único para el front."""

    def parse(self, text: str, **kwargs):
        """
        Si `text` es JSON con 'text' + 'attachments', lo pasa tal cual.
        Si es normal, lo deja en {'text': text, 'attachments': []}
        """
        import json
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "text" in data:
                return data
        except Exception:
            pass
        return {"text": text, "attachments": []}
