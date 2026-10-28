"""لقطات مواقع لمشاهد الريل: يضع المالك رابطاً في المشهد (`shot`) فتُلتقط الصفحة وتظهر في نافذة متصفّح.

تُلتقط مرة واحدة وتُحفظ تحت content/media باسم يحمل بصمة الرابط، فما يراه المالك في المعاينة
هو ما يُنشر، وتغيير الرابط يعني لقطة جديدة تلقائياً.
"""
import hashlib
from pathlib import Path

from config import MEDIA_DIR

VIEW_W, VIEW_H = 1100, 2600            # عرض سطح مكتب ضيّق يُقرأ داخل نافذة الريل، وطول يكفي للتمرير البطيء


def shot_path(post_id: str, index: int, url: str) -> Path:
    tag = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return MEDIA_DIR / f"{post_id}-shot{index:02d}-{tag}.png"


def capture(renderer, url: str, out: Path) -> Path:
    page = renderer._browser.new_page(viewport={"width": VIEW_W, "height": 1400}, device_scale_factor=1)
    try:
        page.goto(url, wait_until="load", timeout=45000)
        try:                                        # مواقع تُبقي اتصالاً مفتوحاً (GitHub مثلاً) لا «تهدأ» أبداً
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(1500)                 # حركات الدخول والخطوط المتأخرة
        height = min(VIEW_H, max(1400, page.evaluate("document.documentElement.scrollHeight")))
        page.set_viewport_size({"width": VIEW_W, "height": height})
        page.wait_for_timeout(500)
        out.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": VIEW_W, "height": height})
    finally:
        page.close()
    return out


def ensure(renderer, post: dict) -> dict[int, Path]:
    """{رقم المشهد (من 1): ملف اللقطة} لكل مشهد فيه رابط. فشل الالتقاط لا يوقف الريل: يبقى المشهد بتصميمه."""
    found: dict[int, Path] = {}
    for i, sc in enumerate((post.get("image") or {}).get("scenes") or [], 1):
        url = str((sc or {}).get("shot") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        path = shot_path(post["id"], i, url)
        if not path.exists():
            try:
                capture(renderer, url, path)
                print(f"[{post['id']}] لقطة المشهد {i}: {url}")
            except Exception as e:  # noqa: BLE001
                print(f"⚠️ [{post['id']}] تعذّر التقاط {url}: {str(e)[:150]}")
                continue
        found[i] = path
    return found
