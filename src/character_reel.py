"""ريل الشخصية الناطقة: حوار بين المهندس شادي (كرتون) وClaude (روبوت بكسل) يشرح موضوعاً من اختيارك.

التدفّق: موضوع ← سكربت JSON (حوار + خطوات + دعوة) ← صوت لكل سطر ← توقيتات من أطوال الصوت الفعلية
← قالب templates/character/reel.html ← التقاط إطارات بـ Playwright ← دمج الصوت بـ ffmpeg.

السكربت يُخزَّن في المنشور نفسه (`image.character`) فيُعدَّل ويُعاد بناؤه، ولا يُنشر شيء قبل موافقتك.

الصوت: Gemini TTS إن وُجد GEMINI_API_KEY (لهجة فلسطينية بالتوجيه)، وإلا أصوات أردنية مجانية من edge-tts.
الاستعمال:
    python character_reel.py --topic "كيف تبدأ مشروعاً بلا ميزانية"     # يكتب مسودة ويبني معاينتها ويرفعها
    python character_reel.py --build <post-id>                            # يعيد بناء فيديو منشور موجود
"""
import json
import os
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

from config import ROOT, OUT_DIR

STYLE = "character"
CHAR_DIR = ROOT / "brand" / "character"
GSAP = ROOT / "templates" / "character" / "gsap.min.js"
FPS = 30
EDGE_VOICES = {"H": "ar-JO-TaimNeural", "C": "ar-JO-SanaNeural"}
GEMINI_VOICES = {"H": "Charon", "C": "Kore"}
GEMINI_TTS_MODELS = [m for m in (os.environ.get("GEMINI_TTS_MODEL"), "gemini-2.5-flash-preview-tts", "gemini-2.5-flash-tts") if m]
KINDS = ("rows", "chips", "checks")

# وسم النبرة → (سرعة %، حدّة Hz) لصوت edge-tts؛ وفي Gemini تدخل في التعليمات المنطوقة
TONE = {"excited": (10, 10), "energetic": (10, 8), "happy": (6, 8), "cheerful": (6, 10), "playful": (5, 8), "proud": (0, 4),
        "confident": (0, 0), "curious": (0, 12), "warm": (-4, 0), "calm": (-8, -4), "serious": (-6, -6), "slowly": (-15, 0),
        "honest": (-4, -2), "smiling": (2, 6)}


class CharacterError(RuntimeError):
    pass


def is_character(post: dict) -> bool:
    img = post.get("image") or {}
    return post.get("template") == "reel" and str(img.get("style") or "") == STYLE and isinstance(img.get("character"), dict)


def plain(text: str) -> str:
    """نص بلا وسوم النبرة ولا علامات التلوين، للعنوان والتحقق."""
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]+\]", "", str(text or "")).replace("**", "")).strip()


def no_tashkeel(text: str) -> str:
    """يحذف التشكيل للعرض فقط؛ الصوت يُولَّد من النص المشكَّل لأنه يحسّن النطق."""
    return re.sub("[ً-ْٰ]", "", text)


def tags_of(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"\[([^\]]+)\]", str(text or ""))]


# ---------------------------------------------------------------- التحقق
def validate_script(sc: dict) -> list[str]:
    """أخطاء السكربت (قائمة فارغة = سليم). تُستعمل في التحقق من الطابور وبعد توليد النموذج."""
    errs: list[str] = []
    if not isinstance(sc, dict):
        return ["image.character يجب أن يكون كائناً"]
    lines = sc.get("lines")
    if not (isinstance(lines, list) and 6 <= len(lines) <= 24):
        return ["الحوار يحتاج من 6 إلى 24 سطراً"]
    ids = []
    for it in lines:
        if not (isinstance(it, (list, tuple)) and len(it) == 3 and it[1] in ("H", "C") and plain(it[2])):
            return ["كل سطر حوار بالشكل [معرّف، H أو C، نص]"]
        if len(plain(it[2])) > 110:
            errs.append(f"السطر {it[0]} أطول من 110 حرفاً")
        ids.append(str(it[0]))
    if len(set(ids)) != len(ids):
        errs.append("معرّفات الحوار مكرّرة")
    steps = sc.get("steps")
    if not (isinstance(steps, list) and 2 <= len(steps) <= 5):
        return errs + ["الخطوات من 2 إلى 5"]
    pos = {i: n for n, i in enumerate(ids)}
    last = -1
    for n, s in enumerate(steps, 1):
        if not isinstance(s, dict) or not plain(s.get("title")):
            errs.append(f"الخطوة {n} بلا عنوان")
            continue
        if str(s.get("at")) not in pos:
            errs.append(f"الخطوة {n}: «at» لا يشير إلى سطر موجود")
        elif pos[str(s["at"])] <= last:
            errs.append(f"الخطوة {n}: ترتيب «at» يجب أن يتصاعد")
        else:
            last = pos[str(s["at"])]
        items = s.get("items")
        if not (isinstance(items, list) and 1 <= len(items) <= 4 and all(plain(x) for x in items)):
            errs.append(f"الخطوة {n}: من 1 إلى 4 عناصر")
        elif any(len(plain(x)) > 38 for x in items):
            errs.append(f"الخطوة {n}: عنصر أطول من 38 حرفاً")
        if s.get("kind", "rows") not in KINDS:
            errs.append(f"الخطوة {n}: نوع غير معروف")
    for key in ("relay_at", "cta_at"):
        if sc.get(key) is not None and str(sc[key]) not in pos:
            errs.append(f"«{key}» لا يشير إلى سطر موجود")
    if not (isinstance(sc.get("hook"), dict) and plain(sc["hook"].get("k2"))):
        errs.append("الافتتاحية تحتاج hook.k2")
    return errs


def normalize(sc: dict) -> dict:
    """يكمّل الافتراضيات: نوع الخطوة، وسطر الخلاصة (الثالث من الآخر) وسطر الدعوة (الأخير)."""
    sc = json.loads(json.dumps(sc))
    ids = [str(x[0]) for x in sc["lines"]]
    sc["lines"] = [[str(a), b, c] for a, b, c in sc["lines"]]
    for s in sc["steps"]:
        s["at"] = str(s["at"])
        s.setdefault("kind", "rows")
        s["items"] = [str(x) for x in s["items"]]
    sc.setdefault("relay_at", ids[max(0, len(ids) - 3)])
    sc.setdefault("cta_at", ids[-1])
    sc["relay_at"], sc["cta_at"] = str(sc["relay_at"]), str(sc["cta_at"])
    sc.setdefault("relay", {})
    sc["relay"].setdefault("nodes", [plain(s["title"])[:16] for s in sc["steps"]])
    sc["relay"].setdefault("title", "")
    sc.setdefault("cta", {})
    sc["hook"].setdefault("k1", "")
    return sc


# ---------------------------------------------------------------- الصوت
def _ffmpeg(*args: str) -> None:
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if p.returncode:
        raise CharacterError(f"ffmpeg: {p.stderr[-300:]}")


def _wav_dur(path: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(p.stdout.strip() or 0)


def _gemini_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "")


def _tts_gemini(text: str, spk: str, out: Path, model: str) -> None:
    import base64

    import requests
    tags = tags_of(text)
    style = ("Speak in a natural, spoken Palestinian Arabic dialect (Levantine, like a young person from Ramallah or Jerusalem), "
             "conversational and clear, not Modern Standard Arabic and not Egyptian. Read exactly this line"
             + (f", in a {', '.join(tags)} tone" if tags else "") + ":\n")
    body = {"contents": [{"parts": [{"text": style + plain(text)}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_VOICES[spk]}}}}}
    for attempt in range(5):
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", json=body, timeout=120,
                          headers={"x-goog-api-key": _gemini_key(), "Content-Type": "application/json"})
        if r.status_code in (429, 500, 503) and attempt < 4:
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code != 200:
            raise CharacterError(f"Gemini TTS {r.status_code}: {r.text[:200]}")
        break
    pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)


def _tts_edge(text: str, spk: str, out: Path) -> None:
    rate, pitch = 0, 0
    for t in tags_of(text):
        if t in TONE:
            rate, pitch = TONE[t]
            break
    clean = plain(text).replace("…", "، ")
    p = subprocess.run([sys.executable, "-m", "edge_tts", "--voice", EDGE_VOICES[spk], f"--rate={rate:+d}%", f"--pitch={pitch:+d}Hz",
                        "--text", clean, "--write-media", str(out)], capture_output=True, text=True)
    if p.returncode:
        raise CharacterError(f"edge-tts: {(p.stderr or p.stdout)[-300:]}")


def synth(lines: list[list[str]], takes: Path, engine: str | None = None) -> str:
    """يولّد ملف صوت لكل سطر ويقصّ الصمت من أطرافه. يرجع المحرّك المستعمل (gemini أو edge)."""
    takes.mkdir(parents=True, exist_ok=True)
    order = [engine] if engine else (["gemini"] if _gemini_key() else []) + ["edge"]
    last_err = ""
    for eng in order:
        try:
            models = GEMINI_TTS_MODELS if eng == "gemini" else [None]
            for model in models:
                try:
                    for n, spk, text in lines:
                        raw = takes / (f"{n}_raw.wav" if eng == "gemini" else f"{n}_raw.mp3")
                        (_tts_gemini(text, spk, raw, model) if eng == "gemini" else _tts_edge(text, spk, raw))
                        _ffmpeg("-i", str(raw), "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                                "silenceremove=start_periods=1:start_threshold=-45dB,areverse", "-ar", "44100", "-ac", "1", str(takes / f"{n}.wav"))
                        print(f"  صوت {n} ({eng}{'/' + model if model else ''})")
                    return eng
                except CharacterError as e:
                    last_err = str(e)
                    if eng != "gemini" or model == models[-1]:
                        raise
        except CharacterError as e:
            last_err = str(e)
            print(f"⚠️ تعذّر محرّك {eng}: {last_err[:160]}")
    raise CharacterError(f"فشل توليد الصوت: {last_err}")


def assemble(sc: dict, takes: Path, work: Path) -> dict:
    """يرتّب الأسطر بفواصل حيّة، ويكتب voice.wav (-14 LUFS) وصوت كل متحدّث، ويرجع التوقيتات."""
    marks = {s["at"] for s in sc["steps"]} | {sc["relay_at"], sc["cta_at"]}
    t, prev, tl = 0.2, None, []
    for n, spk, _ in sc["lines"]:
        if prev is not None:
            t += 0.32 if n in marks else (0.12 if spk != prev else 0.1)
        f = takes / f"{n}.wav"
        d = _wav_dur(f)
        tl.append({"line": n, "spk": spk, "start": round(t, 3), "end": round(t + d, 3), "file": str(f)})
        t += d
        prev = spk
    dur = round(t + 0.9, 2)

    def mix(items, out, norm=False):
        args, fc, lab = [], "", ""
        for i, it in enumerate(items):
            args += ["-i", it["file"]]
            fc += f"[{i}]adelay={int(round(it['start'] * 1000))}[a{i}];"
            lab += f"[a{i}]"
        fc += f"{lab}amix=inputs={len(items)}:normalize=0,apad=whole_dur={dur},atrim=0:{dur}" + (",loudnorm=I=-14:TP=-1.5:LRA=11" if norm else "")
        _ffmpeg(*args, "-filter_complex", fc, "-ar", "48000", "-ac", "1", str(out))

    mix(tl, work / "voice.wav", True)
    mix([x for x in tl if x["spk"] == "H"], work / "H_only.wav")
    mix([x for x in tl if x["spk"] == "C"] or tl[:1], work / "C_only.wav")
    return {"dur": dur, "lines": tl}


def envelope(wav: Path) -> list[float]:
    """علوّ الصوت لكل إطار (0..1): يفتح الفم ويغلقه."""
    n = 48000 // FPS
    e = subprocess.run(["ffmpeg", "-i", str(wav), "-af", f"aresample=48000,asetnsamples={n},astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    return [round(max(0.0, min(1.0, ((float(x) if x != "-inf" else -120.0) + 45) / 30)), 3) for x in re.findall(r"RMS_level=(-?[\d.]+|-inf)", e)]


def estimate_timeline(sc: dict) -> dict:
    """توقيت تقريبي من طول النص، للصورة المصغّرة في اللوحة قبل وجود صوت."""
    marks = {s["at"] for s in sc["steps"]} | {sc["relay_at"], sc["cta_at"]}
    t, tl = 0.2, []
    for n, spk, text in sc["lines"]:
        d = max(1.8, len(plain(text)) * 0.075 + 0.5)
        t += 0.32 if (n in marks and tl) else 0.11 if tl else 0
        tl.append({"line": n, "spk": spk, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return {"dur": round(t + 0.9, 2), "lines": tl}


# ---------------------------------------------------------------- القالب
def build_data(sc: dict, tl: dict, env_h: list[float] | None = None, env_c: list[float] | None = None) -> dict:
    by = {x["line"]: x for x in tl["lines"]}
    text = {n: t for n, _, t in sc["lines"]}
    steps = [dict(title=s["title"], kind=s["kind"], items=s["items"], note=s.get("note", ""), start=by[s["at"]]["start"], end=0.0) for s in sc["steps"]]
    relay_start, cta_start = round(by[sc["relay_at"]]["start"] + 0.2, 2), round(by[sc["cta_at"]]["start"] + 0.2, 2)
    for i, s in enumerate(steps):
        s["end"] = round((steps[i + 1]["start"] - 0.15) if i + 1 < len(steps) else (relay_start - 0.2), 2)
    first = steps[0]["start"]
    return {
        "dur": tl["dur"], "hook": sc["hook"], "hookEnd": round(first - 0.28, 2), "steps": steps,
        "relay": {"title": sc["relay"]["title"], "nodes": sc["relay"]["nodes"], "start": relay_start, "end": round(cta_start - 0.2, 2)},
        "cta": ({**sc["cta"], "start": cta_start} if sc["cta"] else None),
        "lines": [{"s": by[n]["start"], "e": by[n]["end"], "k": spk, "t": no_tashkeel(plain(text[n]))} for n, spk, _ in sc["lines"]],
        "envH": env_h or [], "envC": env_c or [],
    }


def _page(renderer, sc: dict, data: dict, name: str, tmp: Path):
    from jinja2 import Environment, FileSystemLoader

    from config import TEMPLATES_DIR
    from queue_io import load_brand
    brand = str(load_brand().get("name") or "المهندس شادي").split()
    brand_html = (" ".join(brand[:-1]) + " " if len(brand) > 1 else "") + f"<b>{brand[-1]}</b>"
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    html = env.get_template("character/reel.html").render(
        data=data, data_json=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"), brand_html=brand_html, gsap=GSAP.as_uri(),
        images={"closed": (CHAR_DIR / "char_closed_t.png").as_uri(), "open": (CHAR_DIR / "char_open_t.png").as_uri()})
    tmp.mkdir(parents=True, exist_ok=True)
    f = tmp / f"{name}-character.html"
    f.write_text(html, encoding="utf-8")
    page = renderer._browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    page.goto(f.as_uri(), wait_until="domcontentloaded", timeout=60000)   # «load» يتعلّق خلف خطوط Google؛ __ready ينتظر الخطوط بنفسه
    page.wait_for_function("window.__ready === true", timeout=60000)
    return page


def render_poster(renderer, post: dict, out_png: Path, scene: int = 1) -> Path:
    """صورة مصغّرة للوحة بلا صوت: الافتتاحية وأول فقاعة بتوقيت تقديري."""
    sc = normalize(post["image"]["character"])
    page = _page(renderer, sc, build_data(sc, estimate_timeline(sc)), f"{post['id']}-poster", OUT_DIR / "_tmp")
    try:
        page.evaluate("() => { window.__tl.seek(1.4); }")
        out_png.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_png))
    finally:
        page.close()
    return out_png


def render_reel(renderer, post: dict, out_dir: Path) -> Path:
    """يبني الفيديو كاملاً: صوت ← توقيتات ← إطارات ← دمج."""
    import shutil

    sc = normalize(post["image"]["character"])
    errs = validate_script(sc)
    if errs:
        raise CharacterError("سكربت الشخصية غير صالح: " + "؛ ".join(errs))
    work = OUT_DIR / "_character" / post["id"]
    if work.exists():
        shutil.rmtree(work)
    takes, frames = work / "takes", work / "frames"
    frames.mkdir(parents=True)
    engine = synth(sc["lines"], takes)
    tl = assemble(sc, takes, work)
    data = build_data(sc, tl, envelope(work / "H_only.wav"), envelope(work / "C_only.wav"))
    print(f"[{post['id']}] صوت {engine} · المدة {data['dur']}s")
    page = _page(renderer, sc, data, post["id"], work)
    try:
        n = int(data["dur"] * FPS)
        for f in range(n):
            page.evaluate("t => { window.__tl.seek(t); }", f / FPS)
            page.screenshot(path=str(frames / f"{f + 1:05d}.jpg"), type="jpeg", quality=90)
    finally:
        page.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{post['id']}.mp4"
    _ffmpeg("-framerate", str(FPS), "-i", str(frames / "%05d.jpg"), "-i", str(work / "voice.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "20", "-preset", "veryfast", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out))
    shutil.rmtree(work, ignore_errors=True)
    return out


# ---------------------------------------------------------------- كتابة السكربت من الموضوع
def _extract_obj(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise CharacterError("لم يُرجع النموذج JSON")
    return json.loads(text[a:b + 1])


def write_script(topic: str, extra: str = "") -> tuple[dict, dict]:
    """يرجع (سكربت الشخصية، نصوص المنصات) لموضوع المالك."""
    import generator
    prompt = (
        "اكتب سكربت ريل عمودي بصيغة حوار كرتوني بين شخصيتين، موضوعه بالضبط:\n«" + topic.strip() + "»\n" + (extra + "\n" if extra else "") +
        "الشخصيتان: H = المهندس شادي، مضيف فضولي يسأل ويعلّق ويعترض أحياناً. C = Claude، روبوت يشرح ببساطة وبحماس هادئ.\n"
        "اللهجة: فلسطينية محكية بيضاء (بدّي، شو، هيك، كتير، ليش، إنت، لسّا، بس)، وليست فصحى ولا مصرية. جمل قصيرة طبيعية كأن شخصين يتكلمان.\n"
        "الحوار: من 14 إلى 18 سطراً متبادلاً يبدأ بـ H يطرح المشكلة. كل سطر حتى 85 حرفاً ويبدأ بوسم نبرة إنجليزي بين قوسين "
        "من: [excited] [curious] [warm] [calm] [proud] [playful] [confident] [happy] [smiling] [honest]. المعرّفات \"01\" \"02\" … بالترتيب.\n"
        "الخطوات (steps) من 3 إلى 5، لكلٍّ: title (حتى 30 حرفاً وفيه كلمة مفتاحية بين **نجمتين**)، kind (rows أو chips أو checks)، "
        "items (من 2 إلى 4 عناصر، كل عنصر حتى 30 حرفاً)، note اختياري (حتى 50 حرفاً)، و at = معرّف السطر الذي يبدأ عنده الكلام عن هذه الخطوة "
        "(تصاعدي، وأولها لا يسبق السطر 03). الخطوات تشرح الموضوع نفسه بنصائح عملية محددة قابلة للتطبيق.\n"
        "relay_at = معرّف السطر الذي تبدأ عنده الخلاصة، وcta_at = معرّف آخر سطر (دعوة للتعليق).\n"
        "relay = {title: عنوان الخلاصة حتى 30 حرفاً بنجمتين على كلمتين مثل «من **فكرة** لـ **رابط شغّال**»، nodes: اسم قصير (حتى 14 حرفاً) لكل خطوة بنفس عددها وترتيبها}.\n"
        "hook = {k1: جملة صغيرة فوق العنوان حتى 30 حرفاً، k2: العنوان الكبير حتى 45 حرفاً بكلمة أو كلمتين بين **نجمتين** ويمكن فيه \\n لسطر جديد، k3: وسم قصير مثل «5 خطوات»}.\n"
        "cta = {c1: سؤال حتى 40 حرفاً، c2: كلمة مفتاحية حتى 14 حرفاً بين « »، c3: دعوة للتعليق مثل «اكتبها بالتعليقات 👇»}.\n"
        "ممنوع: اختلاق قصص عملاء أو أسماء أو أرقام ونتائج غير حقيقية، أو وعود مبالغ فيها. اشرح الموضوع بمبادئ عامة صحيحة.\n"
        "ثم نصوص المنصات: facebook وinstagram (سطر أول جذّاب، جملتان عن فكرة الريل، سؤال واحد للتعليق، ثم 4 إلى 6 هاشتاقات عربية) "
        "وthreads (حتى 380 حرفاً)، بلا روابط.\n"
        "أرجع كائن JSON واحداً فقط بالمفاتيح: hook, lines (مصفوفة [id, \"H\" أو \"C\", text]), steps, relay_at, cta_at, relay, cta, facebook, instagram, threads.")
    text, _ = generator.generate_text(prompt)
    obj = _extract_obj(text)
    posts = {k: str(obj.pop(k, "")).strip() for k in ("facebook", "instagram", "threads")}
    sc = normalize(obj)
    errs = validate_script(sc)
    if errs:
        raise CharacterError("سكربت غير صالح: " + "؛ ".join(errs))
    return sc, {k: v for k, v in posts.items() if v}


def create_draft(topic: str, extra: str = "") -> dict:
    """مسودة ريل شخصية في الطابور (approved: false). يرجع المنشور."""
    from datetime import timedelta

    import generate
    from queue_io import load_queue, now_local
    sc, platforms = write_script(topic, extra)
    queue = load_queue()
    taken = {str(p["publish_at"]) for p in queue}
    day = (now_local() + timedelta(days=1)).date()
    while f"{day} {generate.REEL_SLOT}" in taken:
        day += timedelta(days=1)
    pid = f"{day}-ch-{int(time.time()) % 100000:05d}"
    title = plain(sc["hook"]["k2"])
    entry = {"id": pid, "approved": False, "publish_at": f"{day} {generate.REEL_SLOT}", "template": "reel",
             "image": {"title": title, "style": STYLE, "seed": 1, "character": sc},
             "platforms": platforms or {"facebook": title, "instagram": title}}
    errors = generate.fatal(generate.validate(queue + [entry]))
    if errors:
        raise CharacterError("فشل التحقق: " + "؛ ".join(errors)[:300])
    generate.append_entries([entry])
    return entry


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    opt = lambda k: a[a.index(k) + 1] if k in a else ""  # noqa: E731
    from queue_io import load_queue
    from render import Renderer
    if opt("--topic"):
        post = create_draft(opt("--topic"), opt("--extra"))
        print("مسودة:", post["id"], "|", post["image"]["title"])
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
                fh.write(f"id={post['id']}\n")
    elif opt("--build"):
        post = next((p for p in load_queue() if p["id"] == opt("--build")), None)
        if not post or not is_character(post):
            print("لا يوجد ريل شخصية بهذا المعرّف")
            return 1
    else:
        print(__doc__)
        return 2
    if "--no-video" in a:
        return 0
    import hosting
    import video
    with Renderer() as r:
        mp4 = render_reel(r, post, OUT_DIR / "_preview")
    final = mp4.with_name(video.preview_name(post))
    mp4.replace(final)
    if "GITHUB_REPOSITORY" in os.environ:
        print("فيديو المعاينة:", next(iter(hosting.upload([final]).values())))
    else:
        print("الفيديو:", final)
    return 0


if __name__ == "__main__":
    sys.exit(main())
