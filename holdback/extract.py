"""
Contract-term extraction.

PDF text is extracted LOCALLY (pdfplumber); only the TEXT is sent to the LLM, never the
file. Provider-agnostic: EXTRACT_PROVIDER picks the backend (gemini default; anthropic
stubbed for a one-line swap). Output is strict JSON where EVERY field is
{value, confidence: 0-1} (CLAUDE.md BOUNTY-01).

Robustness (CLAUDE.md: "the demo cannot die on a parsing miss"): ANY failure — no PDF
text, missing library, bad API response, non-JSON, wrong shape — returns empty_terms()
so the confirm screen simply opens BLANK. This module never raises to the caller.
"""

import json
import os


def empty_terms() -> dict:
    """The full {value, confidence} shape with everything blank (confidence 0)."""
    def blank():
        return {"value": None, "confidence": 0.0}

    return {
        "retention_pct": blank(),
        "trigger1": {"condition": blank(), "pct": blank(), "expected_date": blank()},
        "trigger2": {"condition": blank(), "pct": blank(), "expected_date": blank()},
        "contract_value": blank(),
    }


_PROMPT = """You extract retention terms from a UK construction subcontract.
Return STRICT JSON ONLY (no prose, no markdown fences), EXACTLY this shape, with a
confidence between 0 and 1 for every field:
{
 "retention_pct": {"value": <number, e.g. 5 for 5%>, "confidence": <0-1>},
 "trigger1": {
   "condition": {"value": <text, e.g. "practical completion">, "confidence": <0-1>},
   "pct": {"value": <share of the RETENTION released at this trigger, e.g. 50>, "confidence": <0-1>},
   "expected_date": {"value": <ISO date "YYYY-MM-DD" or null>, "confidence": <0-1>}
 },
 "trigger2": { same shape as trigger1; if there is only one release, use nulls and confidence 0 },
 "contract_value": {"value": <number or null>, "confidence": <0-1>}
}
Rules: retention_pct is a percentage number (5 not 0.05). trigger pct values are the share
of the retention released at that trigger and should sum to 100 across the triggers present.
If a field is absent from the text, set its value to null and confidence to 0.
Contract text follows:
---
"""


def extract_terms(text: str) -> dict:
    """Extract retention terms from contract text. Never raises — returns empty_terms()
    on any problem so the flow degrades to a blank, editable confirm screen."""
    if not text or not text.strip():
        return empty_terms()
    provider = os.environ.get("EXTRACT_PROVIDER", "gemini").lower()
    model = os.environ.get("EXTRACT_MODEL", "gemini-2.5-flash")
    try:
        if provider == "gemini":
            raw = _call_gemini(_PROMPT + text, model)
        elif provider == "anthropic":
            raw = _call_anthropic(_PROMPT + text, model)  # stubbed
        else:
            return empty_terms()
        return _normalise(json.loads(_strip_fences(raw)))
    except Exception:
        # Any failure (network, missing lib, bad JSON, wrong shape) -> blank screen.
        return empty_terms()


def _call_gemini(prompt: str, model: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return resp.text


def _call_anthropic(prompt: str, model: str) -> str:
    # Stubbed on purpose: to switch providers, implement this with the Anthropic SDK
    # (messages.create, same _PROMPT) and set EXTRACT_PROVIDER=anthropic. Untested.
    raise NotImplementedError("anthropic path is stubbed — set EXTRACT_PROVIDER=gemini")


def _strip_fences(raw: str) -> str:
    """Tolerate a model that wraps JSON in ```json ... ``` despite instructions."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.endswith("```"):
            s = s[: s.rfind("```")]
    return s.strip()


def _conf(c) -> float:
    try:
        return max(0.0, min(1.0, float(c)))
    except (TypeError, ValueError):
        return 0.0


def _field(node) -> dict:
    if isinstance(node, dict):
        return {"value": node.get("value"), "confidence": _conf(node.get("confidence"))}
    # Model returned a bare value instead of {value, confidence}
    return {"value": node, "confidence": 0.0}


def _normalise(data: dict) -> dict:
    """Coerce whatever the model returned into the exact empty_terms() shape."""
    out = empty_terms()
    if not isinstance(data, dict):
        return out
    if "retention_pct" in data:
        out["retention_pct"] = _field(data["retention_pct"])
    if "contract_value" in data:
        out["contract_value"] = _field(data["contract_value"])
    for t in ("trigger1", "trigger2"):
        node = data.get(t)
        if isinstance(node, dict):
            for k in ("condition", "pct", "expected_date"):
                if k in node:
                    out[t][k] = _field(node[k])
    return out


def pdf_text(file_storage) -> str:
    """Extract text from an uploaded PDF (a werkzeug FileStorage or file-like object).
    Returns '' on any problem (missing lib, unreadable file) so extraction falls back
    to a blank confirm screen rather than crashing."""
    try:
        import io

        import pdfplumber

        data = file_storage.read()
        parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception:
        return ""
