# apps/agent_service/agents/output_parser.py
from langchain_core.output_parsers import BaseOutputParser

class ScoutParser(BaseOutputParser):
    """Converts tool output into a single message for the frontend."""

    def parse(self, text: str, **kwargs):
        """
        If `text` is JSON with 'text' + 'attachments', passes it as is.
        If it's JSON with just 'url', converts to attachment format.
        If it's normal text, puts it in {'text': text, 'attachments': []}
        """
        import json
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                # If has 'text' key, assume it's already in correct format
                if "text" in data:
                    return data
                # If has 'url' key (dashboard response), convert to attachment format
                if "url" in data:
                    return {
                        "text": "Click the button to view the dashboard",
                        "attachments": [
                            {
                                "type": "url",
                                "url": data["url"],
                                "title": "View Dashboard"
                            }
                        ]
                    }
        except Exception:
            pass
        return {"text": text, "attachments": []}
