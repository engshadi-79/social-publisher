"""يكتب نص إشعار «مسودات جاهزة للمراجعة» (Markdown) إلى الملف الممرَّر، ويطبع عدد المسودات.

يُرسل عبر GitHub Issue (يصل بريدك وتطبيق GitHub مجاناً بلا أسرار إضافية).
لا يكتب شيئاً إن لم تكن هناك مسودات (يرجع 0 ولا ينشئ الملف).
"""
import json
import sys
from pathlib import Path

from config import ROOT
from queue_io import load_queue, now_local, parse_when

DASHBOARD = "https://engshadi-79.github.io/social-publisher/"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    now = now_local()
    drafts = sorted((p for p in load_queue() if not p["approved"] and parse_when(p["publish_at"]) > now),
                    key=lambda p: parse_when(p["publish_at"]))
    if not drafts:
        print(0)
        return 0
    lines = [f"**{len(drafts)} منشور بانتظار موافقتك.** لن يُنشر أي منها قبل أن توافق.", "",
             f"👉 [افتح اللوحة وراجعها]({DASHBOARD}) ثم اضغط «موافقة» أو «وافق على الكل».", "", "| الموعد | القالب | العنوان |", "|---|---|---|"]
    names = {"infographic": "إنفوجرافك", "carousel": "كاروسيل", "reel": "ريل", "split": "صورة", "photo": "صورة"}
    for p in drafts[:20]:
        when = parse_when(p["publish_at"])
        title = str((p.get("image") or {}).get("title", "")).replace("|", "/")[:70]
        lines.append(f"| {when:%m-%d %H:%M} | {names.get(p['template'], p['template'])} | {title} |")
    health = ROOT / "content" / "health.json"
    try:
        h = json.loads(health.read_text(encoding="utf-8"))
        bad = [i for i in h.get("items", []) if i.get("status") in ("bad", "warn")]
        if bad:
            lines += ["", "**⚠️ تنبيهات النظام:**"] + [f"- {i['name']}: {i['detail']}" for i in bad]
    except Exception:  # noqa: BLE001
        pass
    if out:
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(len(drafts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
