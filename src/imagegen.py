"""توليد خلفية تعبّر عن معنى المنشور: Cloudflare Workers AI ثم Pollinations."""
import base64
import io
import os
import time
import urllib.parse
from pathlib import Path

import requests
from PIL import Image

from config import MEDIA_DIR, TEMPLATES

CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
GEMINI_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-nano-banana-2.1")
ASPECT = {(1080, 1080): "1:1", (1080, 1350): "4:5", (1080, 1920): "9:16"}
class NotConfigured(Exception):
    """مزوّد غير مفعّل (لا مفتاح): يُتخطّى بصمت."""


SUFFIX = "no text, no letters, no words, no watermark"


def bg_path(post_id: str) -> Path:
    return MEDIA_DIR / f"{post_id}-bg.png"


def _prompt(post: dict) -> str:
    p = post["image"].get("visual_prompt", "").strip()
    return p if SUFFIX in p else f"{p.rstrip('.,')}, {SUFFIX}"


def _find_image(node):
    """يبحث في ردّ Gemini عن أول كتلة صورة ويرجع base64 (البنية الدقيقة تختلف بين الإصدارات)."""
    if isinstance(node, dict):
        if node.get("type") == "image" and isinstance(node.get("data"), str):
            return node["data"]
        inline = node.get("inlineData") or node.get("inline_data")
        if isinstance(inline, dict) and isinstance(inline.get("data"), str):
            return inline["data"]
        for v in node.values():
            found = _find_image(v)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_image(v)
            if found:
                return found
    return None


def _gemini(prompt: str, size: tuple[int, int]) -> bytes:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise NotConfigured("GEMINI_API_KEY")
    r = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"}, timeout=180,
        json={"model": GEMINI_MODEL,
              "input": [{"type": "text", "text": prompt}],
              "response_format": {"type": "image", "mime_type": "image/jpeg",
                                  "aspect_ratio": ASPECT.get(size, "1:1"), "image_size": "1K"}})
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:  # noqa: BLE001
            msg = r.text
        raise RuntimeError(f"HTTP {r.status_code}: {str(msg)[:200]}")
    data = _find_image(r.json())
    if not data:
        raise RuntimeError("لا توجد صورة في ردّ Gemini")
    return base64.b64decode(data)


def _cloudflare(prompt: str, seed: int | None) -> bytes:
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not (acc and tok):
        raise NotConfigured("CF")
    body = {"prompt": prompt, "steps": 8}
    if seed is not None:
        body["seed"] = seed
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{CF_MODEL}",
        headers={"Authorization": f"Bearer {tok}"}, json=body, timeout=120)
    r.raise_for_status()
    return base64.b64decode(r.json()["result"]["image"])


def _pollinations(prompt: str, seed: int | None, size: tuple[int, int]) -> bytes:
    w, h = size
    q = {"width": w, "height": h, "nologo": "true", "model": "flux"}
    if seed is not None:
        q["seed"] = seed
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?{urllib.parse.urlencode(q)}"
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            if "image" not in r.headers.get("content-type", ""):
                raise RuntimeError("Pollinations لم يُرجع صورة")
            break
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(10 * (attempt + 1))
    else:
        raise last
    # المجاني يضع علامة في الزاوية السفلية؛ نقصّ الشريط السفلي لإزالتها
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    img = img.crop((0, 0, img.width, int(img.height * 0.92)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def ensure_background(post: dict, regen: bool = False, seed: int | None = None):
    """يرجع (المسار أو None، قائمة تحذيرات). لا يرمي أبداً حتى لا يتوقف النشر."""
    warnings: list[str] = []
    path = bg_path(post["id"])
    if path.exists() and not regen:
        return path, warnings
    if not post["image"].get("visual_prompt"):
        return None, ["لا يوجد visual_prompt — خلفية متدرجة"]
    seed = seed if seed is not None else post["image"].get("seed")
    prompt = _prompt(post)
    size = TEMPLATES[post["template"]]
    for name, fn in (("Gemini", lambda: _gemini(prompt, size)),
                     ("Cloudflare", lambda: _cloudflare(prompt, seed)),
                     ("Pollinations", lambda: _pollinations(prompt, seed, size))):
        try:
            data = fn()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return path, warnings
        except NotConfigured:
            continue
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{name} فشل: {type(e).__name__}: {str(e)[:150]}")
    warnings.append("استُعملت خلفية متدرجة بديلة")
    return None, warnings
