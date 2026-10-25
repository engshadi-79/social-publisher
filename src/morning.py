"""ريل الصباح اليومي: عبارات تفاؤل فوق مقاطع حقيقية (قهوة، ورود، شروق، طبيعة).

خلافاً لريلات المحتوى (رسوم متحرّكة مرسومة بالكامل)، الخلفية هنا لقطات حقيقية:
- مع PEXELS_API_KEY: مقاطع فيديو عمودية من Pexels (ترخيص يسمح بالنشر دون إسناد).
- بدونه: صور حقيقية بحركة كاميرا بطيئة (Ken Burns) من سلسلة الصور المعتادة
  (Pexels → Pixabay → Openverse CC0)، فيعمل بلا أي مفتاح.

النص لا يُرسم في ffmpeg (لا يشكّل العربية جيداً): Playwright يرسم طبقتين شفافتين لكل
مشهد بخط Cairo — تظليل ثابت وعبارة تتلاشى — ثم يركّبهما ffmpeg فوق اللقطة.
رابط المقطع يُحفظ في المنشور عند التوليد، فما توافق عليه هو ما يُنشر.
"""
import os
import shutil
import subprocess
from pathlib import Path

import requests

from config import OUT_DIR, TEMPLATES

FPS = 30
XFADE = 0.7                    # مدّة الانتقال المتلاشي بين المشهدين
STYLE = "morning"

# لقطات الصباح المتاحة: يُختار منها بالتناوب يومياً حتى لا تتكرّر الخلفيات
QUERIES = [
    "coffee cup morning", "pink roses", "sunrise nature", "morning sunlight forest", "sea waves sunrise",
    "tea steam window", "flower field", "birds sky morning", "mountain sunrise", "dew drops flower",
    "breakfast sunlight", "tulips garden", "wheat field sunlight", "jasmine flowers", "coffee beans pouring",
    "calm lake morning", "sunflower field", "rain drops window", "lavender field", "clouds sunrise sky",
]


class MorningError(RuntimeError):
    pass


def is_morning(post: dict) -> bool:
    return post.get("template") == "reel" and str((post.get("image") or {}).get("style") or "") == STYLE


def find_video(query: str, pick: int) -> dict | None:
    """مقطع عمودي من Pexels: {video_url, thumb}. None إن لم يكن هناك مفتاح أو نتيجة."""
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    r = requests.get("https://api.pexels.com/videos/search", timeout=30, headers={"Authorization": key},
                     params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 15})
    r.raise_for_status()
    vids = [v for v in r.json().get("videos", []) if 5 <= (v.get("duration") or 0) <= 60]
    for i in range(len(vids)):
        v = vids[(pick + i) % len(vids)]
        files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"
                 and (f.get("height") or 0) > (f.get("width") or 0) and 1280 <= (f.get("height") or 0) <= 2560]
        if files:
            best = min(files, key=lambda f: abs((f.get("height") or 0) - 1920))
            return {"video_url": best["link"], "thumb": v.get("image") or ""}
    return None


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise MorningError("ffmpeg غير موجود")
    return exe


def _run(args: list[str]) -> None:
    p = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise MorningError(f"فشل ffmpeg: {(p.stderr or '')[-400:]}")


def _scenes(post: dict) -> list[dict]:
    return [s or {} for s in (post.get("image") or {}).get("scenes") or []]


def _page_html(post: dict, scene: dict, index: int, layer: str, bg: str = "") -> str:
    from jinja2 import Environment, FileSystemLoader

    from config import TEMPLATES_DIR
    from queue_io import load_brand
    from render import _fonts

    w, h = TEMPLATES["reel"]
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return env.get_template("reel/morning.html").render(
        brand=load_brand(), w=w, h=h, fonts=_fonts(), layer=layer, bg=bg,
        kicker=str(scene.get("kicker") or ("صباح الخير" if index == 1 else "")),
        title=str(scene.get("title", "")), body=str(scene.get("body", "") or ""))


def _shoot(renderer, html: str, name: str, out_png: Path, transparent: bool) -> Path:
    w, h = TEMPLATES["reel"]
    tmp = OUT_DIR / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    page_file = tmp / f"{name}.html"
    page_file.write_text(html, encoding="utf-8")
    page = renderer._browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
    try:
        page.goto(page_file.as_uri(), wait_until="networkidle", timeout=60000)
        page.evaluate("document.fonts.ready")
        out_png.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_png), omit_background=transparent)
    finally:
        page.close()
    return out_png


def _photos(post: dict) -> dict[int, Path]:
    import imagegen
    photos, warns = imagegen.ensure_slide_photos(post, key="scenes")
    for w_ in warns:
        print("⚠️", w_)
    return photos


def render_poster(renderer, post: dict, out_png: Path, scene: int = 1) -> Path:
    """غلاف للمعاينة: اللقطة (صورة المقطع المصغّرة أو الصورة) + التظليل + العبارة."""
    sc = _scenes(post)
    if not sc:
        raise MorningError("لا مشاهد في ريل الصباح")
    s = sc[scene - 1]
    bg = str(s.get("thumb") or "")
    if not bg:
        photo = _photos(post).get(scene)
        bg = photo.as_uri() if photo else ""
    return _shoot(renderer, _page_html(post, s, scene, "poster", bg), f"{post['id']}-mposter{scene}", out_png, False)


def _download(url: str, path: Path) -> Path:
    if path.exists() and path.stat().st_size > 10000:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120, headers={"User-Agent": "social-publisher/1.0"}) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return path


def render_reel(renderer, post: dict, out_dir: Path) -> Path:
    """يبني الريل: مقطع لكل مشهد (لقطة + تظليل + عبارة متلاشية)، ثم انتقالات ناعمة وموسيقى هادئة."""
    from audio import make_track

    sc = _scenes(post)
    if not (3 <= len(sc) <= 8):
        raise MorningError(f"ريل الصباح يحتاج 3 إلى 8 مشاهد (وجدت {len(sc)})")
    w, h = TEMPLATES["reel"]
    work = OUT_DIR / "_morning" / post["id"]
    work.mkdir(parents=True, exist_ok=True)
    photos = None if all(s.get("video_url") for s in sc) else _photos(post)

    clips, durs = [], []
    for i, s in enumerate(sc, 1):
        d = max(3.0, min(8.0, float(s.get("seconds") or 5)))
        shade = _shoot(renderer, _page_html(post, s, i, "shade"), f"{post['id']}-ms{i}", work / f"shade{i}.png", True)
        text = _shoot(renderer, _page_html(post, s, i, "text"), f"{post['id']}-mt{i}", work / f"text{i}.png", True)
        clip = work / f"clip{i}.mp4"
        tx = (f"[2:v]format=rgba,fade=t=in:st=0.45:d=0.8:alpha=1,"
              f"fade=t=out:st={d - XFADE - 0.55:.2f}:d=0.55:alpha=1[tx];[b][1:v]overlay[s];[s][tx]overlay,format=yuv420p[o]")
        if s.get("video_url"):
            src = _download(str(s["video_url"]), work / f"src{i}.mp4")
            _run(["-stream_loop", "-1", "-i", str(src), "-loop", "1", "-i", str(shade), "-loop", "1", "-i", str(text),
                  "-filter_complex",
                  f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS},"
                  f"eq=saturation=1.08[b];" + tx,
                  "-map", "[o]", "-t", f"{d:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(clip)])
        else:
            photo = (photos or {}).get(i)
            if not photo:
                raise MorningError(f"المشهد {i} بلا مقطع ولا صورة (photo_query: {s.get('photo_query')})")
            n = int(d * FPS)
            zin = i % 2 == 1          # تكبير بطيء في مشهد وتصغير في التالي: حركة كاميرا لا تتكرّر
            z = f"1.0+0.12*on/{n}" if zin else f"1.12-0.12*on/{n}"
            _run(["-i", str(photo), "-loop", "1", "-i", str(shade), "-loop", "1", "-i", str(text),
                  "-filter_complex",
                  f"[0:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                  f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={w}x{h}:fps={FPS},setsar=1[b];" + tx,
                  "-map", "[o]", "-t", f"{d:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(clip)])
        clips.append(clip)
        durs.append(d)

    total = sum(durs) - XFADE * (len(durs) - 1)
    starts, acc = [], 0.0
    for d in durs:
        starts.append(acc)
        acc += d - XFADE
    track = make_track(work / "music.wav", total, starts, calm=True)

    inputs, chain, last, off = [], [], "[0:v]", 0.0
    for c in clips:
        inputs += ["-i", str(c)]
    for k in range(1, len(clips)):
        off += durs[k - 1] - XFADE
        tag = f"[x{k}]"
        chain.append(f"{last}[{k}:v]xfade=transition=fade:duration={XFADE}:offset={off:.2f}{tag}")
        last = tag
    chain.append(f"{last}fade=t=in:st=0:d=0.5,fade=t=out:st={total - 0.7:.2f}:d=0.7,format=yuv420p[v]")
    a = len(clips)
    out_mp4 = out_dir / f"{post['id']}.mp4"
    out_dir.mkdir(parents=True, exist_ok=True)
    _run([*inputs, "-i", str(track), "-filter_complex", ";".join(chain), "-map", "[v]", "-map", f"{a}:a",
          "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out_mp4)])
    shutil.rmtree(work, ignore_errors=True)
    return out_mp4
