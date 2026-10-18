"""توليد خلفية تعبّر عن معنى المنشور: Cloudflare Workers AI ثم Pollinations."""
import base64
import os
import urllib.parse
from pathlib import Path

import requests

from config import MEDIA_DIR, TEMPLATES

CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
SUFFIX = "no text, no letters, no words, no watermark"


def bg_path(post_id: str) -> Path:
    return MEDIA_DIR / f"{post_id}-bg.png"


def _prompt(post: dict) -> str:
    p = post["image"].get("visual_prompt", "").strip()
    return p if SUFFIX in p else f"{p.rstrip('.,')}, {SUFFIX}"


def _cloudflare(prompt: str, seed: int | None) -> bytes:
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not (acc and tok):
        raise RuntimeError("CF_ACCOUNT_ID/CF_API_TOKEN غير مضبوطين")
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
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    if "image" not in r.headers.get("content-type", ""):
        raise RuntimeError("Pollinations لم يُرجع صورة")
    return r.content


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
    for name, fn in (("Cloudflare", lambda: _cloudflare(prompt, seed)),
                     ("Pollinations", lambda: _pollinations(prompt, seed, size))):
        try:
            data = fn()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return path, warnings
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{name} فشل: {type(e).__name__}: {str(e)[:150]}")
    warnings.append("استُعملت خلفية متدرجة بديلة")
    return None, warnings
