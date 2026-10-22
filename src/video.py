"""بناء فيديو عمودي (ريل) من مشاهد مصمّمة: Playwright يلتقط الإطارات، وffmpeg يجمعها.

لا يوجد توليد فيديو بالذكاء الاصطناعي مجاناً (كله أرصدة تجريبية أو مدفوع)، فالحركة
هنا مُركّبة من تصاميم العلامة نفسها: صورة حقيقية تتحرّك ببطء، ونصوص تدخل بتتابع.
النصّ يكتبه المولّد، والصور تُجلب من Pexels/Openverse.

الالتقاط إطاراً إطاراً لا تسجيلاً: نستدعي seek(t) في الصفحة قبل كل لقطة، فيخرج
الفيديو نفسه في كل مرة مهما اختلفت سرعة الجهاز.
"""
import shutil
import subprocess
from pathlib import Path

from config import OUT_DIR, TEMPLATES

FPS = 20                     # يكفي لحركة بطيئة، ويوفّر ثلث الإطارات
SCENE_SECONDS = 3.4
FRAME_QUALITY = 92           # إطارات JPEG: ترميز PNG لكل إطار كان يخنق السرعة          # مدّة المشهد الواحد
MIN_SCENES, MAX_SCENES = 3, 8


class VideoError(Exception):
    pass


def ffmpeg_bin() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise VideoError("ffmpeg غير موجود. على GitHub Actions يأتي جاهزاً؛ محلياً ثبّته.")
    return exe


def scene_specs(post: dict) -> list[dict]:
    """يحوّل image.scenes إلى مواصفات رسم: رقم المشهد ومدّته ونصوصه."""
    scenes = (post.get("image") or {}).get("scenes") or []
    n = len(scenes)
    out = []
    for i, s in enumerate(scenes, 1):
        s = s or {}
        out.append({
            "index": i, "total": n,
            "duration": float(s.get("seconds") or SCENE_SECONDS),
            "kicker": str(s.get("kicker", "") or ""),
            "title": str(s.get("title", "")),
            "body": str(s.get("body", "") or ""),
        })
    return out


def _encode(frames_dir: Path, out_mp4: Path, fps: int = FPS) -> Path:
    """H.264 بـ yuv420p: الصيغة الوحيدة التي تقبلها المنصات الخمس جميعاً."""
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_bin(), "-y", "-loglevel", "error",
           "-framerate", str(fps), "-i", str(frames_dir / "%05d.jpg"),
           "-vf", "scale=in_range=full:out_range=tv,format=yuv420p",   # إطارات JPEG مداها كامل؛ المنصات تتوقع yuv420p القياسي
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-color_range", "tv", "-movflags", "+faststart", str(out_mp4)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode or not out_mp4.exists():
        raise VideoError(f"فشل ffmpeg: {(p.stderr or '')[:300]}")
    return out_mp4


def duration_of(post: dict) -> float:
    return sum(s["duration"] for s in scene_specs(post))


def render_poster(renderer, post: dict, out_png: Path, scene: int = 1) -> Path:
    """لقطة غلاف من المشهد الأول عند لحظة اكتمال النصّ.

    اللوحة تعرض هذه بدل بناء الفيديو كاملاً: ثانية واحدة بدل دقيقتين.
    """
    import imagegen
    from jinja2 import Environment, FileSystemLoader

    from config import TEMPLATES_DIR
    from queue_io import load_brand
    from render import _fonts, post_hue

    specs = scene_specs(post)
    if not specs:
        raise VideoError("لا مشاهد في هذا الريل")
    photos, _ = imagegen.ensure_slide_photos(post, key="scenes")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    w, h = TEMPLATES["reel"]
    spec = specs[scene - 1]
    photo = photos.get(scene)
    html = env.get_template("reel/scene.html").render(
        brand=load_brand(), w=w, h=h, fonts=_fonts(),
        photo=photo.as_uri() if photo else None, hue=post_hue(post), **spec)
    tmp = OUT_DIR / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    page_file = tmp / f"{post['id']}-poster{scene}.html"
    page_file.write_text(html, encoding="utf-8")
    page = renderer._browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
    try:
        page.goto(page_file.as_uri())
        page.wait_for_function("window.__ready === true", timeout=30000)
        page.evaluate("t => window.seek(t)", min(1.6, spec["duration"] - 0.6))
        out_png.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": w, "height": h})
    finally:
        page.close()
    return out_png


def render_reel(renderer, post: dict, out_dir: Path, photos: dict[int, Path] | None = None) -> Path:
    """يرسم كل المشاهد إطاراً إطاراً ثم يرمّزها فيديو واحداً."""
    import imagegen
    from jinja2 import Environment, FileSystemLoader

    from config import TEMPLATES_DIR
    from queue_io import load_brand
    from render import _fonts, post_hue

    if photos is None:                    # يجلبها بنفسه كما يفعل الكاروسيل
        photos, warns = imagegen.ensure_slide_photos(post, key="scenes")
        for w_ in warns:                  # لا نُسقطها بصمت: مشهد بلا صورة يجب أن يُرى
            print("⚠️", w_)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    tpl = env.get_template("reel/scene.html")
    brand = load_brand()
    w, h = TEMPLATES["reel"]
    specs = scene_specs(post)
    if not (MIN_SCENES <= len(specs) <= MAX_SCENES):
        raise VideoError(f"الريل يحتاج من {MIN_SCENES} إلى {MAX_SCENES} مشاهد (وجدت {len(specs)})")

    frames = OUT_DIR / "_frames" / post["id"]
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True, exist_ok=True)

    tmp = OUT_DIR / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    n = 0
    for spec in specs:
        photo = (photos or {}).get(spec["index"])
        html = tpl.render(brand=brand, w=w, h=h, fonts=_fonts(),
                          photo=photo.as_uri() if photo else None, hue=post_hue(post), **spec)
        page_file = tmp / f"{post['id']}-reel-{spec['index']}.html"
        page_file.write_text(html, encoding="utf-8")
        page = renderer._browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        try:
            page.goto(page_file.as_uri())
            page.wait_for_function("window.__ready === true", timeout=30000)
            count = max(1, round(spec["duration"] * FPS))
            for f in range(count):
                page.evaluate("t => window.seek(t)", f / FPS)
                n += 1
                page.screenshot(path=str(frames / f"{n:05d}.jpg"), type="jpeg",
                                quality=FRAME_QUALITY)
        finally:
            page.close()

    out_mp4 = out_dir / f"{post['id']}.mp4"
    _encode(frames, out_mp4)
    shutil.rmtree(frames, ignore_errors=True)
    return out_mp4
