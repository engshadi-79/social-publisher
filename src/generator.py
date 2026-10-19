"""استدعاء Gemini لتوليد نصوص المنشورات (الطبقة المجانية للنص كافية).

بحث Google (لهاشتاجات الترند) مجاني فقط مع gemini-2.5-flash، لذلك هو الافتراضي.
"""
import json
import os
import re

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = os.environ.get("GEMINI_TEXT_FALLBACK", "gemini-3.8-flash")


class GeneratorError(Exception):
    pass


def enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _headers():
    return {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}


def _err(r) -> str:
    try:
        return str(r.json().get("error", {}).get("message", r.text))[:220]
    except Exception:  # noqa: BLE001
        return r.text[:220]


def _generate_content(prompt: str, model: str, grounded: bool) -> str:
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.9}}
    if grounded:
        body["tools"] = [{"google_search": {}}]
    r = requests.post(f"{BASE}/models/{model}:generateContent", headers=_headers(), json=body, timeout=180)
    if r.status_code >= 400:
        raise GeneratorError(f"{model} HTTP {r.status_code}: {_err(r)}")
    parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        raise GeneratorError(f"{model}: ردّ فارغ")
    return text


def _find_text(node):
    if isinstance(node, dict):
        if node.get("type") == "text" and isinstance(node.get("text"), str):
            return node["text"]
        for v in node.values():
            t = _find_text(v)
            if t:
                return t
    elif isinstance(node, list):
        for v in reversed(node):
            t = _find_text(v)
            if t:
                return t
    return None


def _interactions(prompt: str, model: str) -> str:
    r = requests.post(f"{BASE}/interactions", headers=_headers(), timeout=180,
                      json={"model": model, "input": prompt})
    if r.status_code >= 400:
        raise GeneratorError(f"{model} (interactions) HTTP {r.status_code}: {_err(r)}")
    text = _find_text(r.json())
    if not text:
        raise GeneratorError(f"{model}: لا نص في الردّ")
    return text


def generate_text(prompt: str):
    """يرجع (النص، وصف الطريقة المستعملة). يجرّب: بحث Google ← بلا بحث ← الواجهة الجديدة."""
    if not enabled():
        raise GeneratorError("GEMINI_API_KEY غير مضبوط")
    attempts = [
        ("2.5-flash + بحث Google (هاشتاجات الترند الحالية)", lambda: _generate_content(prompt, MODEL, True)),
        ("2.5-flash بلا بحث (لم يتوفر بحث Google)", lambda: _generate_content(prompt, MODEL, False)),
        ("نموذج بديل بلا بحث", lambda: _interactions(prompt, FALLBACK_MODEL)),
    ]
    errors = []
    for label, fn in attempts:
        try:
            note = f" — تعذّر سابقاً: {errors[0][:170]}" if errors else ""
            return fn(), label + note
        except (GeneratorError, requests.RequestException) as e:
            errors.append(f"{label}: {e}")
    raise GeneratorError(" | ".join(errors)[:600])


def extract_json(text: str):
    """يستخرج أول مصفوفة JSON من ردّ النموذج (حتى لو لفّها بعلامات ```)."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise GeneratorError("لم يُرجع النموذج قائمة JSON")
    return json.loads(text[start:end + 1])
