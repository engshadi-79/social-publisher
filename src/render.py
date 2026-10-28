"""تحويل قوالب HTML إلى PNG عبر Playwright."""
import hashlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import imagegen
from config import (REEL_STYLES, HUES, INFOGRAPHIC_STYLES, CAROUSEL_STYLES, CAROUSEL_STYLES_FLAT, CAROUSEL_STYLES_PHOTO, OUT_DIR,
                    ROOT, TEMPLATES, TEMPLATES_DIR)
from queue_io import load_brand

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

def _fonts() -> list[dict]:
    out = []
    for f in sorted((ROOT / "brand" / "fonts").glob("*.ttf")):
        n = f.name.lower()
        if "[" in n:
            weight = "200 1000"        # خط متغيّر
        elif "bold" in n or "extrabold" in n or "black" in n:
            weight = "700 900"
        else:
            weight = "400"
        out.append({"uri": f.as_uri(), "weight": weight})
    return out


class Renderer:
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def _shoot(self, html: str, key: str, w: int, h: int, out_png: Path) -> Path:
        tmp = OUT_DIR / "_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        page_file = tmp / f"{key}.html"
        page_file.write_text(html, encoding="utf-8")
        page = self._browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        try:
            page.goto(page_file.as_uri())
            page.wait_for_function("window.__ready === true", timeout=20000)
            out_png.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": w, "height": h})
        finally:
            page.close()
        return out_png

    def render(self, post: dict, out_png: Path, bg: Path | None = None) -> Path:
        """يرسم صورة المنشور (للكاروسيل: الغلاف فقط، استعمل render_post لكل الشرائح)."""
        if post["template"] == "carousel":
            return self.render_slides(post, out_png.parent)[0]
        brand = load_brand()
        w, h = TEMPLATES[post["template"]]
        logo = ROOT / brand.get("logo", "")
        tpl_name = (f"infographic/styles/{infographic_style(post)}.html" if post["template"] == "infographic"
                    else f"{post['template']}/template.html")
        html = _env.get_template(tpl_name).render(
            brand=brand, w=w, h=h, fonts=_fonts(),
            title=post["image"]["title"], body=post["image"].get("body", ""),
            points=[str(x) for x in (post["image"].get("points") or [])],
            bg=bg.as_uri() if bg and bg.exists() else None, hue=post_hue(post),
            vs=post["image"].get("vs"), series=post["image"].get("series", ""),
            logo=logo.as_uri() if brand.get("logo") and logo.is_file() else None,
        )
        return self._shoot(html, post["id"], w, h, out_png)

    def render_slides(self, post: dict, out_dir: Path) -> list[Path]:
        brand = load_brand()
        w, h = TEMPLATES["carousel"]
        style = carousel_style(post)
        photos: dict[int, Path] = {}
        if style in CAROUSEL_STYLES_PHOTO:
            photos, _warns = imagegen.ensure_slide_photos(post)
            if not photos:
                # نمط مصوَّر بلا صورة واحدة يخرج بمربّع فارغ، فننزل إلى نمط لوني
                style = flat_style(post)
        tpl = _env.get_template(f"carousel/styles/{style}.html")
        outs = []
        for spec in slide_specs(post):
            photo = photos.get(spec["index"])
            html = tpl.render(brand=brand, w=w, h=h, fonts=_fonts(), series=post["image"].get("series", ""),
                              photo=photo.as_uri() if photo else None, hue=post_hue(post), **spec)
            outs.append(self._shoot(html, f"{post['id']}-s{spec['index']}", w, h, out_dir / f"{post['id']}-s{spec['index']}.png"))
        return outs

    def render_post(self, post: dict, out_dir: Path, bg: Path | None = None) -> list[Path]:
        """مخرجات المنشور: صورة واحدة، أو شرائح الكاروسيل، أو ملف فيديو الريل."""
        if post["template"] == "carousel":
            return self.render_slides(post, out_dir)
        if post["template"] == "reel":
            import video
            return [video.render_reel(self, post, out_dir)]
        return [self.render(post, out_dir / f"{post['id']}.png", bg)]


def post_hue(post: dict) -> int:
    """إزاحة اللون: `image.hue` إن حُدّدت (0-359)، وإلا تُشتق من المعرّف. القوالب القديمة لا تستعملها."""
    h = (post.get("image") or {}).get("hue")
    if isinstance(h, int) and not isinstance(h, bool) and 0 <= h < 360:
        return h
    if post.get("template") not in ("infographic", "reel", "carousel"):
        return 0
    digest = hashlib.sha1(("hue:" + str(post.get("id", ""))).encode("utf-8")).digest()
    return HUES[digest[0] % len(HUES)]


def reel_style(post: dict) -> str:
    """نمط الريل: `image.style` إن حُدّد، وإلا يُشتق من المعرّف (ثابت لنفس المنشور)."""
    name = str(post.get("image", {}).get("style") or "").strip().lower()
    if name in REEL_STYLES:
        return name
    digest = hashlib.sha1(("reel:" + str(post.get("id", ""))).encode("utf-8")).digest()
    return REEL_STYLES[digest[0] % len(REEL_STYLES)]


def reel_template(post: dict) -> str:
    st = reel_style(post)
    if st == "explainer":
        return "reel/explainer.html"
    if st.startswith("motion"):
        return "reel/motion.html"
    return "reel/scene.html" if st == "geo" else f"reel/styles/{st}.html"


def infographic_style(post: dict) -> str:
    """نمط الإنفوجرافك: `image.style` إن حُدّد، وإلا يُشتق من معرّف المنشور (ثابت لنفس المعرّف)."""
    name = str(post.get("image", {}).get("style") or "").strip().lower()
    if name in INFOGRAPHIC_STYLES:
        return name
    digest = hashlib.sha1(("info:" + str(post.get("id", ""))).encode("utf-8")).digest()
    return INFOGRAPHIC_STYLES[digest[0] % len(INFOGRAPHIC_STYLES)]


def flat_style(post: dict) -> str:
    """نمط لوني (بلا صور) يُشتق من معرّف المنشور: بديلٌ حين تتعذّر الصور."""
    digest = hashlib.sha1(("flat:" + str(post.get("id", ""))).encode("utf-8")).digest()
    return CAROUSEL_STYLES_FLAT[digest[0] % len(CAROUSEL_STYLES_FLAT)]


def carousel_style(post: dict) -> str:
    """نمط الكاروسيل: من `image.style` إن حُدّد، وإلا يُشتق من معرّف المنشور.

    الاشتقاق ثابت لنفس المعرّف (فالصور لا تتغيّر بين معاينة ونشر)، ويوزّع
    المنشورات على الأنماط فلا يخرج منشوران متتاليان بنفس التصميم.
    """
    name = str(post.get("image", {}).get("style") or "").strip().lower()
    if name in CAROUSEL_STYLES:
        return name
    digest = hashlib.sha1(str(post.get("id", "")).encode("utf-8")).digest()
    return CAROUSEL_STYLES[digest[0] % len(CAROUSEL_STYLES)]


def slide_specs(post: dict) -> list[dict]:
    """يحوّل image.slides إلى مواصفات رسم: الغلاف فاتح، الأخيرة (دعوة للتفاعل) بلون العلامة، والبقية متناوبة."""
    slides = post["image"].get("slides") or []
    n, out = len(slides), []
    for i, s in enumerate(slides, 1):
        kind = "cover" if i == 1 else ("cta" if i == n and n > 2 else "content")
        theme = "light" if i == 1 else ("cta" if kind == "cta" else ("dark" if i % 2 == 0 else "light"))
        out.append({"index": i, "total": n, "kind": kind, "theme": theme, "kicker": str(s.get("kicker", "") or ""),
                    "title": str(s.get("title", "")), "body": str(s.get("body", "") or ""),
                    "points": [str(x) for x in (s.get("points") or [])]})
    return out
