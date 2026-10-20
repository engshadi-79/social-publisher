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
REALISM = "photorealistic, real photograph, natural lighting, shot on a DSLR camera, sharp focus"


def post_bg_path(post: dict) -> Path:
    """مسار الخلفية المخزّنة: للنسخة المعاد نشرها يشير image.bg_from إلى المنشور الأصلي."""
    return bg_path((post.get("image") or {}).get("bg_from") or post["id"])


def bg_path(post_id: str) -> Path:
    return MEDIA_DIR / f"{post_id}-bg.png"


def _prompt(post: dict) -> str:
    p = post["image"].get("visual_prompt", "").strip()
    if "photo" not in p.lower():
        p = f"{p.rstrip('.,')}, {REALISM}"
    return p if SUFFIX in p else f"{p.rstrip('.,')}, {SUFFIX}"


def _pexels(query: str, size: tuple[int, int], pick: int) -> bytes:
    """صورة فوتوغرافية حقيقية مجانية من Pexels (ترخيص يسمح بالنشر دون إسناد)."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise NotConfigured("PEXELS_API_KEY")
    orient = "square" if size[0] == size[1] else "portrait"
    r = requests.get("https://api.pexels.com/v1/search", timeout=30,
                     headers={"Authorization": key},
                     params={"query": query, "orientation": orient, "size": "large", "per_page": 15})
    r.raise_for_status()
    photos = r.json().get("photos", [])
    if not photos:
        raise RuntimeError(f"لا نتائج في Pexels لـ «{query}»")
    ph = photos[pick % len(photos)]
    img = requests.get(ph["src"].get("large2x") or ph["src"]["large"], timeout=60)
    img.raise_for_status()
    return img.content


def _openverse(query: str, size: tuple[int, int], pick: int) -> bytes:
    """صور حقيقية CC0/ملكية عامة من Openverse: بلا مفتاح وبلا حاجة لإسناد."""
    words = query.split()
    variants = [" ".join(words[:n]) for n in (len(words), 3, 2, 1) if n and n <= len(words)]
    cands = []
    for v in dict.fromkeys(variants):
        r = requests.get("https://api.openverse.org/v1/images/", timeout=30,
                         headers={"User-Agent": "social-publisher/1.0"},
                         params={"q": v, "license": "cc0,pdm", "category": "photograph",
                                 "page_size": 20, "mature": "false"})
        r.raise_for_status()
        found = [x for x in r.json().get("results", []) if x.get("url")]
        for min_w in (2000, 1600, 1300, 1000):      # نفضّل الأعلى دقة، ثم نتساهل
            cands = [x for x in found if (x.get("width") or 0) >= min_w]
            if cands:
                break
        if cands:
            break
    if not cands:
        raise RuntimeError(f"لا نتائج مناسبة في Openverse لـ «{query}»")
    last = None
    for i in range(min(5, len(cands))):
        c = cands[(pick + i) % len(cands)]
        try:
            img = requests.get(c["url"], timeout=60, headers={"User-Agent": "social-publisher/1.0"})
            img.raise_for_status()
            im = Image.open(io.BytesIO(img.content)).convert("RGB")
            if im.width < 900 or im.height < 600:
                continue
            im.thumbnail((2000, 2000))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=90)
            return buf.getvalue()
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"تعذّر تنزيل صورة صالحة من Openverse ({last})")


def _pixabay(query: str, size: tuple[int, int], pick: int) -> bytes:
    """صورة فوتوغرافية حقيقية مجانية من Pixabay (يسمح الترخيص بالنشر دون إسناد)."""
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise NotConfigured("PIXABAY_API_KEY")
    orient = "all" if size[0] == size[1] else "vertical"
    r = requests.get("https://pixabay.com/api/", timeout=30, params={
        "key": key, "q": query, "image_type": "photo", "orientation": orient,
        "min_width": 800, "safesearch": "true", "per_page": 20, "order": "popular"})
    r.raise_for_status()
    hits = r.json().get("hits", [])
    if not hits:
        raise RuntimeError(f"لا نتائج في Pixabay لـ «{query}»")
    img = requests.get(hits[pick % len(hits)]["largeImageURL"], timeout=60)
    img.raise_for_status()
    return img.content


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
        if r.status_code == 429 and "Free Tier" in str(msg):
            raise NotConfigured("Gemini: المشروع على الطبقة المجانية، لا توليد صور")
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
    path = post_bg_path(post)
    if path.exists() and not regen:
        return path, warnings
    if not (post["image"].get("visual_prompt") or post["image"].get("photo_query")):
        return None, ["لا يوجد visual_prompt ولا photo_query — خلفية متدرجة"]
    seed = seed if seed is not None else post["image"].get("seed")
    if post["image"].get("visual_prompt"):
        prompt = _prompt(post)
    else:  # وصف احتياطي مبني على كلمات البحث ليبقى مرتبطاً بالموضوع
        prompt = f"{post['image']['photo_query']}, {REALISM}, empty space for text, {SUFFIX}"
    size = TEMPLATES[post["template"]]
    chain = []
    query = post["image"].get("photo_query")
    if query:
        chain.append(("Pexels", lambda: _pexels(query, size, seed or 0)))
    if query:
        chain.append(("Pixabay", lambda: _pixabay(query, size, seed or 0)))
        chain.append(("Openverse", lambda: _openverse(query, size, seed or 0)))
    chain += [("Gemini", lambda: _gemini(prompt, size)),
              ("Cloudflare", lambda: _cloudflare(prompt, seed)),
              ("Pollinations", lambda: _pollinations(prompt, seed, size))]
    for name, fn in chain:
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
