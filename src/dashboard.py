"""يولّد لوحة تحكم ثابتة (HTML) من الطابور والحالة، لتُنشر على GitHub Pages."""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from PIL import Image

import accounts as acc
import imagegen
from config import ROOT, MEDIA_DIR, OUT_DIR, PLATFORMS, SITE_URL, TIMEZONE, TOPICS_PATH
from queue_io import load_queue, load_state, now_local, parse_when
from render import Renderer

LABELS = {"facebook": "فيسبوك", "instagram": "إنستغرام", "threads": "ثريدز",
          "linkedin": "لينكدإن", "telegram": "تيليجرام"}
SITE = OUT_DIR / "dashboard"
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")


def img_token(pid: str) -> str:
    """لاحقة غير قابلة للتخمين في أسماء صور المعاينة، مشتقة من كلمة المرور، فلا يصل لها من لا يعرفها."""
    if not PASSWORD:
        return ""
    return "-" + hmac.new(PASSWORD.encode("utf-8"), ("img:" + pid).encode("utf-8"), hashlib.sha256).hexdigest()[:14]


def encrypt_page(html: str) -> str:
    """يغلّف صفحة اللوحة بتشفير AES-GCM (مفتاح من PBKDF2) ويُفكّ في المتصفح بكلمة المرور."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    iters, salt, iv = 250000, os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iters).derive(PASSWORD.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, html.encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    payload = json.dumps({"salt": b64(salt), "iv": b64(iv), "iter": iters, "ct": b64(ct)})
    gate = Environment(loader=FileSystemLoader(str(Path(__file__).parent)), autoescape=True).get_template("gate_template.html")
    return gate.render(payload=payload)


def when_ar(d):
    h = d.hour % 12 or 12
    part = "صباحاً" if d.hour < 12 else "مساءً"
    return f"يوم {DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} الساعة {h}:{d.minute:02d} {part}"


def join_ar(names):
    return " و".join(names)


IG_SWITCH = "2026-10-20T05:48"   # لحظة تحويل إنستغرام من ostoraplus إلى engshadi2011


def _chip(name, text, st, scheduled_txt, label=None):
    status = st.get("status")
    if status == "published":
        txt, cls, hint = "✅ نُشر", "published", st.get("published_at", "")
    elif status == "failed":
        txt, cls, hint = "❌ لم ينجح", "failed", "فشل بعد كل المحاولات"
    elif status == "retry":
        txt, cls, hint = "🔁 ستُعاد المحاولة", "retry", ""
    else:
        txt, cls, hint = scheduled_txt, "", ""
    url = None
    if name == "facebook" and status == "published" and st.get("platform_post_id"):
        url = f"https://www.facebook.com/{st['platform_post_id']}"
    if status == "published" and st.get("account"):
        label = st["account"]
    elif status == "published" and name == "instagram" and str(st.get("published_at", "9"))[:16] < IG_SWITCH:
        label = "إنستغرام — ostoraplus"          # منشور قبل تحويل الحساب
    return {"label": label or LABELS[name], "txt": txt, "status": cls, "hint": hint, "url": url,
            "text": text, "error": st.get("error") if status in ("failed", "retry") else None}


def build(posts, state, now):
    items = []
    for p in posts:
        when = parse_when(p["publish_at"])
        st = state.get(p["id"], {})
        past = when <= now
        tgs = acc.targets_of(p)
        multi = {pl for pl in {t.platform for t in tgs} if sum(1 for t in tgs if t.platform == pl) > 1 or not next(t for t in tgs if t.platform == pl).account.default}
        chips = [_chip(t.platform, p["platforms"][t.platform], st.get(t.key, {}), "⏳ ينتظر دوره" if past else "⏳ ينتظر موعده",
                       label=t.account.label if t.platform in multi or len(acc.load_accounts()) > len(acc.defaults()) else None)
                 for t in tgs]
        statuses = [c["status"] for c in chips]
        all_done = all(s == "published" for s in statuses)
        if not p["approved"]:
            group, badge, badge_txt = "draft", "draft", "بانتظار موافقتك"
        elif "failed" in statuses or "retry" in statuses:
            group = "failed"
            badge, badge_txt = ("failed", "حدثت مشكلة") if "failed" in statuses else ("retry", "ستُعاد المحاولة")
        elif all_done:
            group, badge, badge_txt = "published", "published", "تم النشر"
        elif past:
            group, badge, badge_txt = "upcoming", "due", "سيُنشر خلال دقائق"
        else:
            group, badge, badge_txt = "upcoming", "scheduled", "سيُنشر في موعده"
        pl = join_ar(dict.fromkeys(c["label"] for c in chips))
        line = {
            "draft": f"لن يُنشر حتى توافق عليه. الموعد المقترح: {when_ar(when)}. المنصات: {pl}.",
            "published": f"نُشر على: {pl}.",
            "failed": f"حدثت مشكلة عند النشر ({pl}). التفاصيل أدناه.",
            "upcoming": (f"حان موعده وسيُنشر خلال دقائق على: {pl}." if past
                         else f"سيُنشر {when_ar(when)} على: {pl}."),
        }[group]
        items.append({"line": line, "when_ar": when_ar(when),
            "id": p["id"], "template": p["template"], "topic": p.get("topic", ""), "title": p["image"]["title"],
            "when": when, "when_txt": when.strftime("%Y-%m-%d %H:%M"), "chips": chips,
            "group": group, "badge": badge, "badge_txt": badge_txt,
            "platforms_txt": "، ".join(LABELS[n] for n in p["platforms"]),
        })
    # الأحدث أولاً للمنشورة، والأقرب أولاً للقادمة
    items.sort(key=lambda x: x["when"])
    upcoming = [i for i in items if i["group"] == "upcoming"]
    rest = [i for i in items if i["group"] != "upcoming"][::-1]
    ordered = upcoming + rest
    counts = {g: sum(1 for i in items if i["group"] == g) for g in ("upcoming", "published", "draft", "failed")}
    parts = []
    if upcoming:
        parts.append(f"يوجد {counts['upcoming']} منشور مجدول، وأقربها {upcoming[0]['when_ar']}.")
    else:
        parts.append("لا يوجد أي منشور مجدول حالياً.")
    if counts["draft"]:
        parts.append(f"{counts['draft']} منشور ينتظر موافقتك ولن يُنشر قبلها.")
    if counts["failed"]:
        parts.append(f"⚠️ {counts['failed']} منشور فيه مشكلة وتحتاج نظرة.")
    if counts["published"]:
        parts.append(f"تم نشر {counts['published']} منشور حتى الآن.")
    counts["summary"] = " ".join(parts)
    return ordered, counts, (upcoming[0] if upcoming else None)


def load_topics() -> list[dict]:
    if not TOPICS_PATH.exists():
        return []
    data = yaml.safe_load(TOPICS_PATH.read_text(encoding="utf-8")) or {}
    return [t for t in (data.get("topics") or []) if isinstance(t, dict) and t.get("id")]


def load_health():
    f = ROOT / "content" / "health.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except Exception:  # noqa: BLE001
        return None


def load_scripts():
    f = ROOT / "content" / "scripts.json"
    try:
        return (json.loads(f.read_text(encoding="utf-8")).get("weeks") or [])[:3] if f.exists() else []
    except Exception:  # noqa: BLE001
        return []


def load_settings() -> dict:
    """إعدادات تكتبها اللوحة (content/settings.json)، مثل النشر التلقائي لريل الصباح."""
    f = ROOT / "content" / "settings.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def load_gen_log():
    f = ROOT / "content" / "generate_log.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=SITE)
    ap.add_argument("--publish", action="store_true", help="ارفع اللوحة إلى gh-pages (داخل Actions)")
    ap.add_argument("--vercel", action="store_true", help="ابنِ اللوحة لـ Vercel (vercel-site/public)، بلا تشفير: الحماية على الخادم")
    args = ap.parse_args()
    global PASSWORD
    if args.vercel:
        PASSWORD = ""                      # الحماية في middleware الخادم، فلا تشفير ولا أسماء صور مموّهة
        args.out = ROOT / "vercel-site" / "public"
        args.publish = False
        if args.out.exists():
            import shutil
            shutil.rmtree(args.out)

    posts, state, now = load_queue(), load_state(), now_local()
    items, counts, nxt = build(posts, state, now)

    img_dir = args.out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    by_id = {p["id"]: p for p in posts}
    with Renderer() as r:
        for it in items:
            post = by_id[it["id"]]
            bg = imagegen.post_bg_path(post)
            if post["template"] == "reel":      # لقطة غلاف بدل بناء الفيديو كاملاً
                import video
                n_sc = len((post.get("image") or {}).get("scenes") or []) or 1    # كل مشهد بلقطته ليراجعها صاحبها (ريل الشخصية: لقطة واحدة)
                pngs = [video.render_poster(r, post, OUT_DIR / "_tmp" / f"{post['id']}-poster{k}.png", k) for k in range(1, n_sc + 1)]
            else:
                pngs = r.render_post(post, OUT_DIR / "_tmp", bg if bg.exists() else None)
            fulls = []
            for n, png in enumerate(pngs, 1):
                im = Image.open(png).convert("RGB")
                tok = img_token(it["id"])
                name = f"full-{it['id']}{tok}.jpg" if len(pngs) == 1 else f"full-{it['id']}{tok}-s{n}.jpg"
                im.save(img_dir / name, quality=85)
                fulls.append("images/" + name)
                if n == 1:
                    th = im.copy()
                    th.thumbnail((540, 960))
                    th.save(img_dir / f"thumb-{it['id']}{tok}.jpg", quality=82)
            it["slides_json"] = json.dumps(fulls) if len(fulls) > 1 else ""
            it["slide_count"] = len(fulls)
            it["tok"] = img_token(it["id"])
            it["reel_scenes"] = (len((post.get("image") or {}).get("scenes") or []) or len(((post.get("image") or {}).get("character") or {}).get("steps") or [])) if post["template"] == "reel" else 0
            if post["template"] == "reel":      # فيديو المعاينة (يُبنى عند الطلب) باسم يحمل بصمة المحتوى
                import video
                it["vname"] = video.preview_name(post)
            it["morning"] = str((post.get("image") or {}).get("style") or "") == "morning"

    acc_json = json.dumps([{"id": a.id, "platform": a.platform, "label": a.label, "default": a.default}
                           for a in acc.load_accounts().values()], ensure_ascii=False).replace("</", "<\\/")
    group_of = {it["id"]: it["group"] for it in items}
    raw = {}
    for p in posts:
        e = json.loads(json.dumps(p, default=lambda o: o.strftime("%Y-%m-%d %H:%M") if hasattr(o, "strftime") else str(o)))
        e["publish_at"] = parse_when(p["publish_at"]).strftime("%Y-%m-%d %H:%M")
        e["group"] = group_of.get(p["id"], "draft")
        e["tok"] = img_token(p["id"])          # الصفحة الرئيسية تعرض الصور المصغّرة من JS
        raw[p["id"]] = e
    ins_f = ROOT / "content" / "insights.json"
    insights_json = (ins_f.read_text(encoding="utf-8") if ins_f.exists() else "{}").replace("</", "<\\/")
    posts_json = json.dumps(raw, ensure_ascii=False).replace("</", "<\\/")

    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent)), autoescape=True)
    html = env.get_template("dashboard_template.html").render(
        topics_js=((Path(__file__).parent / "dashboard_topics.js").read_text(encoding="utf-8") + "\n" +
                   (Path(__file__).parent / "dashboard_posts.js").read_text(encoding="utf-8") + "\n" +
                   (Path(__file__).parent / "dashboard_extra.js").read_text(encoding="utf-8") + "\n" +
                   (Path(__file__).parent / "dashboard_home.js").read_text(encoding="utf-8")).replace("__REPO__", os.environ.get("GITHUB_REPOSITORY", "engshadi-79/social-publisher")),
        gen_log=load_gen_log(), health=load_health(), health_json=json.dumps(load_health() or {}, ensure_ascii=False).replace("</", "<\\/"), settings=load_settings(), settings_json=json.dumps(load_settings(), ensure_ascii=False).replace("</", "<\\/"), proxy=args.vercel, posts_json=posts_json, acc_json=acc_json, scripts=load_scripts(), utm=[(LABELS[p], f"{SITE_URL}?utm_source={p}&utm_medium=social&utm_campaign=bio") for p in ("instagram", "facebook", "threads", "linkedin", "telegram")], pages_base="https://" + os.environ.get("GITHUB_REPOSITORY", "engshadi-79/social-publisher").replace("/", ".github.io/", 1) + "/", insights_json=insights_json,
        topics=load_topics(), repo=os.environ.get("GITHUB_REPOSITORY", "engshadi-79/social-publisher"),
        posts=items, counts=counts, next_post=nxt, tz=TIMEZONE,
        updated=now.strftime("%Y-%m-%d %H:%M"))
    if PASSWORD:
        html = encrypt_page(html)
        print("اللوحة مشفّرة بكلمة المرور")
    else:
        print("اللوحة بلا تشفير (محمية على الخادم)" if args.vercel else "تنبيه: DASHBOARD_PASSWORD غير مضبوط، اللوحة مفتوحة لكل من معه الرابط")
    redirect = os.environ.get("DASHBOARD_URL", "")
    if args.publish and redirect:           # اللوحة صارت على Vercel: صفحة GitHub القديمة تحوّل إليها ولا تحمل أي محتوى
        # الصفحة نفسها عنوان العودة لتفويض Threads (setup_threads.py): إن وصلها ?code= تعرضه للنسخ ولا تحوّل
        html = ('<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
                '<meta name="viewport" content="width=device-width,initial-scale=1"><title>لوحة التحكم</title></head>'
                '<body style="font-family:sans-serif;text-align:center;padding:40px;line-height:1.8">'
                f'<div id="go"><a href="{redirect}">انتقل إلى لوحة التحكم</a></div>'
                '<div id="code" hidden><h2>كود التفويض جاهز ✅</h2><p>انسخه والصقه في نافذة PowerShell التي تنتظره:</p>'
                '<textarea id="c" readonly style="width:min(92vw,560px);height:90px;font:16px monospace;direction:ltr"></textarea>'
                '<p><button id="b" style="font-size:18px;padding:8px 22px">نسخ</button></p></div>'
                '<script>var m=/[?&]code=([^&#]+)/.exec(location.search);'
                'if(m){document.getElementById("go").hidden=true;document.getElementById("code").hidden=false;'
                'var t=document.getElementById("c");t.value=decodeURIComponent(m[1]);t.select();'
                'document.getElementById("b").onclick=function(){t.select();try{navigator.clipboard.writeText(t.value)}catch(e){document.execCommand("copy")}this.textContent="نُسخ ✓"}}'
                f'else location.replace("{redirect}");</script></body></html>')
    (args.out / "index.html").write_text(html, encoding="utf-8")
    if args.vercel:        # صفحة 404 تعيد التحميل تلقائياً: بعد كل حفظ يُنشر الموقع من جديد وقد تتأخر الملفات لحظات
        (args.out / "404.html").write_text('<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><meta http-equiv="refresh" content="4;url=/"><title>جارٍ التحديث</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1018;color:#e6eaf2;font-family:Segoe UI,Tahoma,sans-serif;text-align:center}p{color:#9aa4b5}.s{width:34px;height:34px;border:4px solid #243044;border-top-color:#2dd4bf;border-radius:50%;margin:0 auto 14px;animation:r 1s linear infinite}@keyframes r{to{transform:rotate(360deg)}}</style></head><body><div><div class="s"></div><h2>جارٍ تحديث اللوحة…</h2><p>تُنشر نسخة جديدة بعد حفظك. ستُعاد الصفحة تلقائياً خلال ثوانٍ.</p></div></body></html>', encoding="utf-8")
    print(f"لوحة: {args.out / 'index.html'}  ({len(items)} منشور)")
    if args.publish:
        import hosting
        print("نُشرت على:", hosting.upload_site(args.out, with_images=not redirect))
    return 0


if __name__ == "__main__":
    sys.exit(main())
