"""يغيّر حساب إنستغرام فقط (دون المساس بصفحة فيسبوك): يضبط IG_USER_ID و IG_PAGE_TOKEN
في أسرار GitHub من الصفحة المربوط بها الحساب الجديد. لا يطبع أي توكن ولا يحفظه في ملف.

الاستعمال:  python scripts/setup_instagram.py
المطلوب: توكن مستخدم قصير من Graph API Explorer، مولَّد وأنت تختار «الصفحة المربوط بها حساب إنستغرام الجديد».
"""
import getpass
import subprocess
import sys

import requests

REPO = "engshadi-79/social-publisher"
V = "https://graph.facebook.com/v21.0"


def get(path, **params):
    r = requests.get(f"{V}/{path}", params=params, timeout=30)
    d = r.json()
    if r.status_code != 200 or "error" in d:
        sys.exit(f"خطأ من Meta: {d.get('error', {}).get('message', r.text[:200])}")
    return d


def secret(name, value):
    p = subprocess.run(["gh", "secret", "set", name, "-R", REPO], input=value, text=True, capture_output=True)
    if p.returncode:
        sys.exit(f"فشل ضبط {name}: {p.stderr[:200]}")
    print(f"✓ {name}")


def main():
    app_id = input("App ID (تطبيق social-publisher): ").strip()
    app_secret = getpass.getpass("App Secret (مخفي): ").strip()
    short = getpass.getpass("التوكن القصير من Graph API Explorer (مخفي): ").strip()

    long_user = get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
                    client_secret=app_secret, fb_exchange_token=short)["access_token"]
    pages = get("me/accounts", access_token=long_user, limit=100,
                fields="id,name,access_token,instagram_business_account{id,username}").get("data", [])
    linked = [p for p in pages if p.get("instagram_business_account")]
    if not linked:
        sys.exit("لا توجد صفحة مربوطة بحساب إنستغرام احترافي ضمن هذا التوكن. تأكد من ربط الحساب بالصفحة ومن اختيار الصفحة عند توليد التوكن.")
    for i, p in enumerate(linked):
        ig = p["instagram_business_account"]
        print(f"[{i}] صفحة «{p['name']}» ← إنستغرام @{ig.get('username', '?')}")
    pick = linked[int(input("رقم الحساب المطلوب: ")) if len(linked) > 1 else 0]
    ig = pick["instagram_business_account"]

    secret("IG_USER_ID", ig["id"])
    secret("IG_PAGE_TOKEN", pick["access_token"])
    print(f"تم: سيُنشر إنستغرام الآن على @{ig.get('username', '?')} عبر صفحة «{pick['name']}». فيسبوك لم يتغيّر.")


if __name__ == "__main__":
    main()
