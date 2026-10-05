import json
import re


from config import MODEL

_client = None


def ask_json(system: str, user: str, max_tokens: int = 8000):
    """Call Claude and parse the reply as JSON. Needs ANTHROPIC_API_KEY set."""
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    msg = _client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)
