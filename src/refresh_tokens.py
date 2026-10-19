"""تجديد توكن Threads طويل الأمد وتحديث سرّ GitHub."""
import os
import subprocess
import sys

import requests


def main() -> int:
    tok = os.environ.get("THREADS_TOKEN")
    if not tok:
        print("THREADS_TOKEN غير مضبوط")
        return 1
    r = requests.get("https://graph.threads.net/refresh_access_token", timeout=30,
                     params={"grant_type": "th_refresh_token", "access_token": tok})
    if r.status_code != 200:
        print(f"فشل التجديد: HTTP {r.status_code} {r.text[:200].replace(tok, '***')}")
        return 1
    new = r.json()["access_token"]
    print(f"::add-mask::{new}")
    env = {**os.environ, "GH_TOKEN": os.environ["GH_PAT"]}
    p = subprocess.run(["gh", "secret", "set", "THREADS_TOKEN", "--repo", os.environ["GITHUB_REPOSITORY"]],
                       input=new, text=True, env=env, capture_output=True)
    if p.returncode:
        print("فشل تحديث السرّ:", p.stderr[:200])
        return 1
    import json, datetime, pathlib
    pathlib.Path(__file__).resolve().parent.parent.joinpath("content", "token_dates.json").write_text(
        json.dumps({"threads_token_issued": datetime.date.today().isoformat()}, indent=2) + chr(10), encoding="utf-8")
    print("تم تجديد THREADS_TOKEN (صالح 60 يوماً إضافياً)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
