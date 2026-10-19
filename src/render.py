"""تحويل قوالب HTML إلى PNG عبر Playwright."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import OUT_DIR, ROOT, TEMPLATES, TEMPLATES_DIR
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

    def render(self, post: dict, out_png: Path, bg: Path | None = None) -> Path:
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
        tmp = OUT_DIR / "_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        page_file = tmp / f"{post['id']}.html"
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
