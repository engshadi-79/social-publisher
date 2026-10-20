"""تحويل قوالب HTML إلى PNG عبر Playwright."""
import hashlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

import imagegen
from config import (CAROUSEL_STYLES, CAROUSEL_STYLES_PHOTO, OUT_DIR, ROOT,
                    TEMPLATES, TEMPLATES_DIR)
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
        html = _env.get_template(f"{post['template']}/template.html").render(
            brand=brand, w=w, h=h, fonts=_fonts(),
            title=post["image"]["title"], body=post["image"].get("body", ""),
            points=[str(x) for x in (post["image"].get("points") or [])],
            bg=bg.as_uri() if bg and bg.exists() else None,
            logo=logo.as_uri() if brand.get("logo") and logo.is_file() else None,
        )
        return self._shoot(html, post["id"], w, h, out_png)

    def render_slides(self, post: dict, out_dir: Path) -> list[Path]:
        brand = load_brand()
        w, h = TEMPLATES["carousel"]
        style = carousel_style(post)
        tpl = _env.get_template(f"carousel/styles/{style}.html")
        photos: dict[int, Path] = {}
        if style in CAROUSEL_STYLES_PHOTO:
            photos, _warns = imagegen.ensure_slide_photos(post)
        outs = []
        for spec in slide_specs(post):
            photo = photos.get(spec["index"])
            html = tpl.render(brand=brand, w=w, h=h, fonts=_fonts(),
                              photo=photo.as_uri() if photo else None, **spec)
            outs.append(self._shoot(html, f"{post['id']}-s{spec['index']}", w, h, out_dir / f"{post['id']}-s{spec['index']}.png"))
        return outs

    def render_post(self, post: dict, out_dir: Path, bg: Path | None = None) -> list[Path]:
        """كل صور المنشور: صورة واحدة أو كل شرائح الكاروسيل."""
        if post["template"] == "carousel":
            return self.render_slides(post, out_dir)
        return [self.render(post, out_dir / f"{post['id']}.png", bg)]


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
