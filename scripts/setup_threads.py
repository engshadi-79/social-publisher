"""يحوّل كود التفويض من Threads إلى توكن طويل الأمد (60 يوماً) ويكتب THREADS_USER_ID و THREADS_TOKEN
في أسرار GitHub. لا يطبع أي توكن ولا يحفظه في ملف.

الاستعمال:  python scripts/setup_threads.py
"""
import getpass
import subprocess
import sys
import urllib.parse

import requests

REPO = "engshadi-79/social-publisher"
REDIRECT = "https://engshadi-79.github.io/social-publisher/"
SCOPES = "threads_basic,threads_content_publish,threads_manage_insights"   # الأخير لقراءة المشاهدات والإعجابات


def secret(name, value):
    p = subprocess.run(["gh", "secret", "set", name, "-R", REPO], input=value, text=True, capture_output=True)
    if p.returncode:
        sys.exit(f"فشل ضبط {name}: {p.stderr[:200]}")
    print(f"✓ {name}")


def check(r, what):
    d = r.json()
    if r.status_code != 200 or "error" in d:
        err = d.get("error", d)
        msg = err.get("message") if isinstance(err, dict) else err
        sys.exit(f"خطأ في {what}: {str(msg)[:250]}")
    return d


def main():
    app_id = input("Threads App ID: ").strip()
    app_secret = getpass.getpass("Threads App Secret (مخفي): ").strip()

    url = "https://threads.net/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": app_id, "redirect_uri": REDIRECT, "scope": SCOPES, "response_type": "code"})
    print("\nافتح هذا الرابط في المتصفح ووافق، ثم انسخ قيمة code من شريط العنوان بعد التحويل:")
    print(url + "\n")
    code = input("code (الصقه كاملاً، وسأحذف #_ تلقائياً): ").strip().split("#")[0]
    if "code=" in code:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [code])[0]

    short = check(requests.post("https://graph.threads.net/oauth/access_token", timeout=30, data={
        "client_id": app_id, "client_secret": app_secret, "grant_type": "authorization_code",
        "redirect_uri": REDIRECT, "code": code}), "تبادل الكود")
    long = check(requests.get("https://graph.threads.net/access_token", timeout=30, params={
        "grant_type": "th_exchange_token", "client_secret": app_secret,
        "access_token": short["access_token"]}), "التوكن الطويل")

    secret("THREADS_USER_ID", str(short["user_id"]))
    secret("THREADS_TOKEN", long["access_token"])
    print(f"صلاحية التوكن: {long.get('expires_in', 0) // 86400} يوماً (يجدّده refresh-tokens.yml أسبوعياً)")


if __name__ == "__main__":
    main()
