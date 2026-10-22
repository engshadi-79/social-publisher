"""يسحب أرقام الأداء (إعجابات، تعليقات، وصول، مشاهدات) للمنشورات المنشورة ويكتب content/insights.json.

كل منصة تحتاج صلاحية قراءة مختلفة في توكنها؛ إن رُفض الطلب يُسجَّل السبب بدل أن يفشل التشغيل،
وتعرض اللوحة «—» مع ملاحظة بدل رقم مختلق. لا يغيّر شيئاً في المنصات (قراءة فقط).
"""
import json
import os
import sys
from datetime import datetime, timezone

import requests

from accounts import load_accounts, secret_values
from config import GRAPH_VERSION, ROOT, STATE_PATH, THREADS_VERSION

OUT = ROOT / "content" / "insights.json"
G = f"https://graph.facebook.com/{GRAPH_VERSION}"
TH = f"https://graph.threads.net/{THREADS_VERSION}"
MAX_POSTS = 60                       # أحدث المنشورات فقط، فلا نستهلك حدّ الطلبات


def clean(msg: str) -> str:
    for v in secret_values():
        msg = msg.replace(v, "***")
    return msg[:160]


def get(url, **params):
    r = requests.get(url, params=params, timeout=30)
    d = r.json()
    if r.status_code != 200 or "error" in d:
        raise RuntimeError(str((d.get("error") or {}).get("message", r.text)))
    return d


def metrics_of(d: dict) -> dict:
    return {m["name"]: (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value")) for m in d.get("data", [])}


def facebook(pid, c):
    tok = c["token"]
    d = get(f"{G}/{pid}", fields="reactions.summary(true).limit(0),comments.summary(true).limit(0),shares", access_token=tok)
    out = {"likes": d.get("reactions", {}).get("summary", {}).get("total_count"),
           "comments": d.get("comments", {}).get("summary", {}).get("total_count"),
           "shares": (d.get("shares") or {}).get("count", 0)}
    try:                                   # الوصول يحتاج read_insights؛ اختياري
        out["reach"] = metrics_of(get(f"{G}/{pid}/insights", metric="post_impressions_unique", access_token=tok)).get("post_impressions_unique")
    except Exception:  # noqa: BLE001
        pass
    return out


def instagram(pid, c):
    tok = c["token"]
    d = get(f"{G}/{pid}", fields="like_count,comments_count", access_token=tok)
    out = {"likes": d.get("like_count"), "comments": d.get("comments_count")}
    try:
        out.update(metrics_of(get(f"{G}/{pid}/insights", metric="reach,saved,shares", access_token=tok)))
    except Exception:  # noqa: BLE001
        pass
    return out


def threads(pid, c):
    m = metrics_of(get(f"{TH}/{pid}/insights", metric="views,likes,replies,reposts,quotes", access_token=c["token"]))
    return {"views": m.get("views"), "likes": m.get("likes"), "comments": m.get("replies"), "shares": (m.get("reposts") or 0) + (m.get("quotes") or 0)}


FETCH = {"facebook": facebook, "instagram": instagram, "threads": threads}


def account_for(key: str, accounts):
    plat, _, aid = key.partition(":")
    if aid:
        return accounts.get(aid)
    return next((a for a in accounts.values() if a.platform == plat and a.default), None)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    accounts = load_accounts()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rows = []
    for pid, per in state.items():
        for key, st in per.items():
            if st.get("status") == "published" and st.get("platform_post_id"):
                rows.append((st.get("published_at", ""), pid, key, st))
    rows.sort(reverse=True)
    res, ok, bad = {}, 0, 0
    for _, pid, key, st in rows[:MAX_POSTS]:
        plat = key.split(":")[0]
        fn, acct = FETCH.get(plat), account_for(key, accounts)
        entry = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="minutes")}
        if fn and acct and acct.creds().get("token"):
            try:
                entry.update({k: v for k, v in fn(st["platform_post_id"], acct.creds()).items() if v is not None})
                ok += 1
            except Exception as e:  # noqa: BLE001
                entry["error"] = clean(str(e))
                prev = (old.get(pid) or {}).get(key) or {}
                entry.update({k: v for k, v in prev.items() if k not in ("error", "fetched_at") and isinstance(v, (int, float))})
                bad += 1
        else:
            entry["error"] = "المنصة لا تدعم الإحصاءات بعد" if not fn else "لا توكن"
        res.setdefault(pid, {})[key] = entry
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"إحصاءات: {ok} ناجحة، {bad} فشلت، من {min(len(rows), MAX_POSTS)} منشور")
    for pid, per in list(res.items())[:6]:
        for k, v in per.items():
            print(" ", pid, k, {a: b for a, b in v.items() if a != "fetched_at"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
