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
    from render import _fonts, post_hue, reel_template

    import character_reel
    if character_reel.is_character(post):     # ريل الشخصية: الافتتاحية وأول فقاعة
        return character_reel.render_poster(renderer, post, out_png, scene)
    import morning
    if morning.is_morning(post):          # ريل الصباح: لقطات حقيقية لا رسوم
        return morning.render_poster(renderer, post, out_png, scene)
    specs = scene_specs(post)
    if not specs:
        raise VideoError("لا مشاهد في هذا الريل")
    if is_motion(post):
        return render_motion_poster(renderer, post, out_png, scene)
    photos, _ = imagegen.ensure_slide_photos(post, key="scenes")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    w, h = TEMPLATES["reel"]
    spec = specs[scene - 1]
    photo = photos.get(scene)
    html = env.get_template(reel_template(post)).render(
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
        page.evaluate("t => window.seek(t)", min(2.4, spec["duration"] - 0.6))
        out_png.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": w, "height": h})
    finally:
        page.close()
    return out_png


def render_reel(renderer, post: dict, out_dir: Path, photos: dict[int, Path] | None = None,
                use_preview: bool = True) -> Path:
    """يرسم كل المشاهد إطاراً إطاراً ثم يرمّزها فيديو واحداً (أو يأخذ فيديو المعاينة المبني لنفس المحتوى)."""
    import imagegen
    from jinja2 import Environment, FileSystemLoader

    from config import TEMPLATES_DIR
    from queue_io import load_brand
    from render import _fonts, post_hue, reel_template

    if use_preview:
        ready = fetch_preview(post, out_dir)
        if ready:
            return ready
    import character_reel
    if character_reel.is_character(post):     # يبني صوتاً وفيديو كاملاً (دقائق): الأفضل أن تكون المعاينة مبنية سلفاً
        return character_reel.render_reel(renderer, post, out_dir)
    import morning
    if morning.is_morning(post):
        return morning.render_reel(renderer, post, out_dir)
    if is_motion(post):
        return render_motion_reel(renderer, post, out_dir)
    if photos is None:                    # يجلبها بنفسه كما يفعل الكاروسيل
        photos, warns = imagegen.ensure_slide_photos(post, key="scenes")
        for w_ in warns:                  # لا نُسقطها بصمت: مشهد بلا صورة يجب أن يُرى
            print("⚠️", w_)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    tpl = env.get_template(reel_template(post))
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


# ================= محرّك «موشن»: صفحة واحدة لكل الفيديو + موسيقى مركّبة =================
BEAT = 0.5                    # 120 نبضة/دقيقة: المشاهد تبدأ وتنتهي على النبض
CAPTURE_FPS = 48              # نلتقط ضعف معدّل الإخراج ثم ندمج كل إطارين = تمويه حركة طبيعي
OUT_FPS = 24
MOTION_THEMES = {
    "motion": {"a1": "#6366f1", "a2": "#8b5cf6", "bg1": "#070b16", "bg2": "#1b1f4b", "ink": "#ffffff", "kick": "#f59e0b",
               "cols": ["#6366f1", "#8b5cf6", "#10b981", "#f59e0b", "#ec4899", "#06b6d4", "#6366f1", "#a855f7"]},
    "motion-sunset": {"a1": "#f97316", "a2": "#ec4899", "bg1": "#170914", "bg2": "#4a1d2e", "ink": "#ffffff", "kick": "#6366f1",
                      "cols": ["#f97316", "#ec4899", "#f59e0b", "#ef4444", "#a855f7", "#fb7185", "#f97316", "#facc15"]},
    "explainer": {"a1": "#ff7a1a", "a2": "#ffb347", "bg1": "#0f1013", "bg2": "#1c1d22", "ink": "#ffffff", "kick": "#ff7a1a",
                  "cols": ["#ff7a1a"]},
    "motion-mint": {"a1": "#10b981", "a2": "#06b6d4", "bg1": "#04161a", "bg2": "#0f3b3a", "ink": "#ffffff", "kick": "#f43f5e",
                    "cols": ["#10b981", "#06b6d4", "#22d3ee", "#84cc16", "#14b8a6", "#38bdf8", "#10b981", "#a3e635"]},
}


def preview_key(post: dict) -> str:
    """بصمة محتوى الريل: تتغيّر مع أي تعديل في المشاهد أو النمط، فلا يُعرض فيديو قديم بعد التعديل."""
    import hashlib
    import json
    blob = json.dumps(post.get("image") or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def preview_name(post: dict) -> str:
    """اسم فيديو المعاينة على gh-pages/images (تبنيه reel-preview.yml عند الطلب من اللوحة)."""
    return f"preview-{post['id']}-{preview_key(post)}.mp4"


def fetch_preview(post: dict, out_dir: Path) -> Path | None:
    """إن بُني فيديو معاينة لنفس المحتوى فهو ما رآه صاحبه ووافق عليه: يُنشر كما هو بلا إعادة بناء."""
    import os

    import requests
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    owner, name = repo.split("/")
    url = f"https://{owner}.github.io/{name}/images/{preview_name(post)}"
    try:
        r = requests.get(url, timeout=120)
        if r.status_code != 200 or len(r.content) < 50000:
            return None
    except requests.RequestException:
        return None
    out = out_dir / f"{post['id']}.mp4"
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    print(f"[{post['id']}] استُعمل فيديو المعاينة المعتمد ({len(r.content) // 1024} KB)")
    return out


def is_motion(post: dict) -> bool:
    from render import reel_style
    return reel_style(post) in MOTION_THEMES


def motion_timing(post: dict) -> tuple[list[float], list[float], float]:
    """مدد المشاهد مقرّبة إلى أقرب نبضة (5 نبضات على الأقل)، ونبضة أخيرة يعود فيها الشكل لهيئته الأولى (حلقة)."""
    durs = [max(5, round(s["duration"] / BEAT)) * BEAT for s in scene_specs(post)]
    starts, t = [], 0.0
    for d in durs:
        starts.append(t)
        t += d
    return starts, durs, t + BEAT


def _motion_page(renderer, post: dict):
    from jinja2 import Environment, FileSystemLoader

    from config import TEMPLATES_DIR
    from queue_io import load_brand
    from render import _fonts, post_hue, reel_style, reel_template

    specs = scene_specs(post)
    if not (MIN_SCENES <= len(specs) <= MAX_SCENES):
        raise VideoError(f"الريل يحتاج من {MIN_SCENES} إلى {MAX_SCENES} مشاهد (وجدت {len(specs)})")
    starts, durs, total = motion_timing(post)
    import shots                                        # لقطات المواقع لمشاهد فيها رابط
    caps = shots.ensure(renderer, post)
    from urllib.parse import urlparse
    raw = (post.get("image") or {}).get("scenes") or []
    for sp in specs:
        sp["shot"] = caps[sp["index"]].as_uri() if sp["index"] in caps else ""
        sp["shot_host"] = urlparse(str((raw[sp["index"] - 1] or {}).get("shot") or "")).netloc
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    w, h = TEMPLATES["reel"]
    html = env.get_template(reel_template(post)).render(
        brand=load_brand(), w=w, h=h, fonts=_fonts(), hue=0, theme=MOTION_THEMES[reel_style(post)],   # الثيم يحدد الألوان، فلا إزاحة لونية
        scenes=specs, starts=starts, durs=durs, total=total, series=(post.get("image") or {}).get("series", ""))
    tmp = OUT_DIR / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    page_file = tmp / f"{post['id']}-motion.html"
    page_file.write_text(html, encoding="utf-8")
    page = renderer._browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
    page.goto(page_file.as_uri())
    page.wait_for_function("window.__ready === true", timeout=30000)
    return page, w, h, starts, durs, total


def render_motion_poster(renderer, post: dict, out_png: Path, scene: int = 1) -> Path:
    page, w, h, starts, durs, _ = _motion_page(renderer, post)
    try:
        k = max(0, min(scene - 1, len(starts) - 1))
        page.evaluate("t => window.seek(t)", starts[k] + min(durs[k] - 0.5, 1.8))
        out_png.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_png), clip={"x": 0, "y": 0, "width": w, "height": h})
    finally:
        page.close()
    return out_png


def render_motion_reel(renderer, post: dict, out_dir: Path) -> Path:
    import audio

    frames = OUT_DIR / "_frames" / post["id"]
    if frames.exists():
        shutil.rmtree(frames)
    frames.mkdir(parents=True, exist_ok=True)
    page, w, h, starts, durs, total = _motion_page(renderer, post)
    try:
        count = int(round(total * CAPTURE_FPS))
        for f in range(count):
            page.evaluate("t => window.seek(t)", f / CAPTURE_FPS)
            page.screenshot(path=str(frames / f"{f + 1:05d}.jpg"), type="jpeg", quality=FRAME_QUALITY)
    finally:
        page.close()
    wav = audio.make_track(frames / "track.wav", total, starts)
    out_mp4 = out_dir / f"{post['id']}.mp4"
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_bin(), "-y", "-loglevel", "error",
           "-framerate", str(CAPTURE_FPS), "-i", str(frames / "%05d.jpg"), "-i", str(wav),
           "-vf", f"tmix=frames=2,fps={OUT_FPS},scale=in_range=full:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-color_range", "tv",
           "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out_mp4)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode or not out_mp4.exists():
        raise VideoError(f"فشل ffmpeg: {(p.stderr or '')[:300]}")
    shutil.rmtree(frames, ignore_errors=True)
    return out_mp4
