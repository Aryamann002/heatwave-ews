"""Optional Groq LLM client (OpenAI-compatible). Used only for wording, never for alert levels.

Every caller must work when this returns None: no key, network failure, or a bad reply.
"""

import json
import os
from typing import Any
from urllib.request import Request, urlopen

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def chat(system: str, user: str, *, json_mode: bool = False, timeout: float = 15) -> str | None:
    """Return the model's reply text, or None if the LLM is unavailable for any reason."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    body: dict[str, Any] = {
        "model": MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    request = Request(
        GROQ_URL,
        data=json.dumps(body).encode(),
        # Groq's edge rejects the default Python-urllib user agent.
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "heatwave-ews/1.0"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
