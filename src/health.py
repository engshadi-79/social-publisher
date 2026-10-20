"""فحص صحة النظام وكتابة content/health.json (تعرضها اللوحة).

الحالات: ok سليم · warn تنبيه · bad مشكلة · off غير مفعّل (اختياري).
"""
import json
import os
import sys
from datetime import date, datetime, timezone

import requests

from accounts import load_accounts
from config import GRAPH_VERSION, ROOT, THREADS_VERSION

OUT = ROOT / "content" / "health.json"
DATES = ROOT / "content" / "token_dates.json"
SECRETS = ("FB_PAGE_TOKEN", "IG_PAGE_TOKEN", "THREADS_TOKEN", "TELEGRAM_BOT_TOKEN", "CF_API_TOKEN", "GH_PAT",
           "GEMINI_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY", "GITHUB_TOKEN")
THREADS_LIFETIME_DAYS = 60


def clean(msg: str) -> str:
    for k in SECRETS:
        v = os.environ.get(k)
        if v:
            msg = msg.replace(v, "***")
    return msg[:170]


def item(name, status, detail):
    return {"name": name, "status": status, "detail": detail}


def graph_check(name, need, url, params, field):
    if not all(os.environ.get(k) for k in need):
        return item(name, "bad", "الأسرار غير مضبوطة")
    try:
        r = requests.get(url, params=params, timeout=30)
        d = r.json()
        if r.status_code != 200 or "error" in d:
            return item(name, "bad", clean(str(d.get("error", {}).get("message", r.text))))
        return item(name, "ok", f"متصل: {d.get(field, '')}")
    except Exception as e:  # noqa: BLE001
        return item(name, "bad", clean(f"{type(e).__name__}: {e}"))


def threads_expiry():
    issued = None
    try:
        issued = date.fromisoformat(json.loads(DATES.read_text(encoding="utf-8")).get("threads_token_issued", ""))
    except Exception:  # noqa: BLE001
        pass
    if not issued:
        return item("صلاحية توكن ثريدز", "warn", "تاريخ الإصدار غير معروف")
    left = THREADS_LIFETIME_DAYS - (date.today() - issued).days
    auto = bool(os.environ.get("GH_PAT"))
    if left <= 3:
        return item("صلاحية توكن ثريدز", "bad", f"ينتهي خلال {max(left, 0)} يوم! جدّده الآن")
    if left <= 14 and not auto:
        return item("صلاحية توكن ثريدز", "warn", f"ينتهي بعد {left} يوماً والتجديد التلقائي غير مفعّل (أضف GH_PAT)")
    if not auto:
        return item("صلاحية توكن ثريدز", "warn", f"ينتهي بعد {left} يوماً. فعّل التجديد التلقائي بإضافة سرّ GH_PAT")
    return item("صلاحية توكن ثريدز", "ok", f"ينتهي بعد {left} يوماً ويتجدد تلقائياً")


def publish_runs():
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (tok and repo):
        return item("تشغيل النشر الدوري", "off", "يُفحص داخل GitHub فقط")
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/actions/workflows/publish.yml/runs",
                         params={"per_page": 1, "event": "schedule"},
                         headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}, timeout=30)
        runs = r.json().get("workflow_runs", [])
        if not runs:
            return item("تشغيل النشر الدوري", "warn", "لم يعمل الجدول الدوري بعد")
        run = runs[0]
        when = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        hours = (datetime.now(timezone.utc) - when).total_seconds() / 3600
        if run.get("conclusion") not in ("success", None):
            return item("تشغيل النشر الدوري", "bad", f"آخر تشغيل انتهى بـ {run['conclusion']}")
        if hours > 6:
            return item("تشغيل النشر الدوري", "warn", f"آخر تشغيل دوري قبل {hours:.0f} ساعة (قد يتأخر جدول GitHub)")
        return item("تشغيل النشر الدوري", "ok", f"آخر تشغيل قبل {max(int(hours * 60), 1)} دقيقة")
    except Exception as e:  # noqa: BLE001
        return item("تشغيل النشر الدوري", "warn", clean(f"تعذّر الفحص: {e}"))


def check_account(a):
    """فحص اتصال حساب واحد من accounts.yaml."""
    c = a.creds()
    if a.platform == "telegram":
        ok = bool(c.get("token") and c.get("chat_id"))
        return item(a.label, "ok" if ok else "off", "مُعدّ" if ok else "غير مُعدّ بعد (اختياري)")
    need = ("page_id", "token") if a.platform == "facebook" else ("user_id", "token") if a.platform == "instagram" else ("token",)
    if not all(c.get(r) for r in need):
        return item(a.label, "bad", "الأسرار غير مضبوطة")
    tok = {"access_token": c["token"]}
    if a.platform == "facebook":
        return graph_check(a.label, [], f"https://graph.facebook.com/{GRAPH_VERSION}/{c['page_id']}", {"fields": "name", **tok}, "name")
    if a.platform == "instagram":
        return graph_check(a.label, [], f"https://graph.facebook.com/{GRAPH_VERSION}/{c['user_id']}", {"fields": "username", **tok}, "username")
    return graph_check(a.label, [], f"https://graph.threads.net/{THREADS_VERSION}/me", {"fields": "username", **tok}, "username")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    items = [check_account(a) for a in load_accounts().values()]
    items += [
        threads_expiry(),
        item("توليد النصوص (Gemini)", "ok" if os.environ.get("GEMINI_API_KEY") else "off",
             "مفتاح موجود" if os.environ.get("GEMINI_API_KEY") else "لا مفتاح: زر التوليد لن يعمل"),
        item("صور حقيقية", "ok", "Pixabay" if os.environ.get("PIXABAY_API_KEY") else
             ("Pexels" if os.environ.get("PEXELS_API_KEY") else "Openverse (مجاني بلا مفتاح)")),
        publish_runs(),
    ]
    bad = sum(1 for i in items if i["status"] == "bad")
    warn = sum(1 for i in items if i["status"] == "warn")
    OUT.write_text(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                               "bad": bad, "warn": warn, "items": items}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for i in items:
        print(f"[{i['status']}] {i['name']}: {i['detail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
