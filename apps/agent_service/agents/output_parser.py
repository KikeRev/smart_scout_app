# apps/agent_service/agents/output_parser.py
from langchain_core.output_parsers import BaseOutputParser

class ScoutParser(BaseOutputParser):
    """Converts tool output into a single message for the frontend."""

    def parse(self, text: str, **kwargs):
        """
        If `text` is JSON with 'text' + 'attachments', passes it as is.
        If it's normal, puts it in {'text': text, 'attachments': []}
        """
        import json
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "text" in data:
                return data
        except Exception:
            pass
        return {"text": text, "attachments": []}
