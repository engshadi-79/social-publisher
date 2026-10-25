"""يحوّل توكن Graph API Explorer القصير إلى FB_PAGE_ID / FB_PAGE_TOKEN / IG_USER_ID
ويكتبها مباشرة في أسرار GitHub. لا يطبع أي توكن ولا يحفظه في ملف.

الاستعمال:  python scripts/setup_meta.py

صلاحيات التوكن في Graph API Explorer (ضع علامة على كلٍّ منها قبل Generate Access Token):
  النشر:      pages_show_list, pages_manage_posts, pages_read_engagement, business_management,
              instagram_basic, instagram_content_publish
  الإحصاءات:  read_insights, pages_read_user_content, instagram_manage_insights
بدون صلاحيتَي read_insights و pages_read_user_content تبقى أرقام فيسبوك فارغة في اللوحة.
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
    app_id = input("App ID: ").strip()
    app_secret = getpass.getpass("App Secret (مخفي): ").strip()
    short = getpass.getpass("التوكن القصير من Graph API Explorer (مخفي): ").strip()

    long_user = get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
                    client_secret=app_secret, fb_exchange_token=short)["access_token"]
    pages = get("me/accounts", access_token=long_user, fields="id,name,access_token,instagram_business_account").get("data", [])
    if not pages:
        sys.exit("لا توجد صفحات: تأكد من اختيار صفحتك عند توليد التوكن ومن الصلاحيات")
    for i, p in enumerate(pages):
        print(f"[{i}] {p['name']}  (إنستغرام: {'مربوط' if p.get('instagram_business_account') else 'غير مربوط'})")
    page = pages[int(input("رقم الصفحة: ")) if len(pages) > 1 else 0]
    ig = page.get("instagram_business_account", {}).get("id")

    secret("FB_PAGE_ID", page["id"])
    secret("FB_PAGE_TOKEN", page["access_token"])
    if ig:
        secret("IG_USER_ID", ig)
    else:
        print("⚠️ لا يوجد حساب إنستغرام Business/Creator مربوط بهذه الصفحة؛ لم يُضبط IG_USER_ID")


if __name__ == "__main__":
    main()
