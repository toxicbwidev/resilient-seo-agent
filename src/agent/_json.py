"""Small JSON helper: extract a JSON payload from LLM output that may wrap
it in a markdown fence or surrounding prose."""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


def extract_json(raw: str) -> Any:
    """Parse JSON from a model response that may have a code fence around it.

    Raises ValueError if the result is not valid JSON. Callers should catch
    and treat as a malformed-output failure (recoverable by retry)."""
    s = raw.strip()
    m = _FENCE.match(s)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"model returned invalid JSON: {e.msg!r}") from e
