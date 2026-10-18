"""مولّد نصوص اختياري عبر Gemini (الطبقة المجانية). معطّل افتراضياً.

لا يُستدعى من أي مكان تلقائياً؛ الكتابة المعتادة يقوم بها Claude Code مسبقاً.
للتفعيل: اضبط GEMINI_API_KEY ثم استورد generate() يدوياً.
"""
import os

import requests

MODEL = "gemini-2.0-flash"


def enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def generate(prompt: str) -> str:
    if not enabled():
        raise RuntimeError("المولّد معطّل: لا يوجد GEMINI_API_KEY")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, timeout=60,
        json={"contents": [{"parts": [{"text": prompt}]}]})
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]
