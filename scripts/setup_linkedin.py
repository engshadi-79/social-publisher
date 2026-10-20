"""يحوّل كود تفويض لينكدإن إلى توكن (60 يوماً)، ويكتب LINKEDIN_TOKEN و LINKEDIN_AUTHOR_URN
في أسرار GitHub، ويسجّل تاريخ الإصدار ليُنبّهك فحص الصحة قبل انتهائه.
لا يطبع أي توكن ولا يحفظه في ملف.

الاستعمال:  python scripts/setup_linkedin.py
يُعاد تشغيله كل 60 يوماً: التجديد البرمجي مقصور على شركاء MDP المعتمدين.
"""
import getpass
import json
import subprocess
import sys
import urllib.parse
from datetime import date
from pathlib import Path

import requests

REPO = "engshadi-79/social-publisher"
REDIRECT = "https://engshadi-79.github.io/social-publisher/"
SCOPES = "openid profile w_member_social"
DATES = Path(__file__).resolve().parent.parent / "content" / "token_dates.json"


def secret(name, value):
    p = subprocess.run(["gh", "secret", "set", name, "-R", REPO], input=value, text=True, capture_output=True)
    if p.returncode:
        sys.exit(f"فشل ضبط {name}: {p.stderr[:200]}")
    print(f"✓ {name}")


def check(r, what):
    if r.status_code != 200:
        try:
            d = r.json()
        except Exception:  # noqa: BLE001
            d = {}
        msg = d.get("error_description") or d.get("message") or r.text
        sys.exit(f"خطأ في {what}: {str(msg)[:250]}")
    return r.json()


def main():
    client_id = input("LinkedIn Client ID: ").strip()
    client_secret = getpass.getpass("LinkedIn Client Secret (مخفي): ").strip()

    url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
        "scope": SCOPES, "state": "shadi"})
    print("\nافتح هذا الرابط ووافق، ثم انسخ رابط الصفحة التي حُوّلت إليها كاملاً:")
    print(url + "\n")
    code = input("الرابط أو قيمة code: ").strip()
    if "code=" in code:
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [code])[0]

    tok = check(requests.post("https://www.linkedin.com/oauth/v2/accessToken", timeout=30, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": client_id, "client_secret": client_secret}), "تبادل الكود")
    access = tok["access_token"]

    me = check(requests.get("https://api.linkedin.com/v2/userinfo", timeout=30,
                            headers={"Authorization": f"Bearer {access}"}), "قراءة الحساب")
    author = f"urn:li:person:{me['sub']}"

    secret("LINKEDIN_TOKEN", access)
    secret("LINKEDIN_AUTHOR_URN", author)

    data = {}
    if DATES.exists():
        try:
            data = json.loads(DATES.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    data["linkedin_token_issued"] = date.today().isoformat()
    DATES.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\nالحساب: {me.get('name', '')}")
    print(f"صلاحية التوكن: {tok.get('expires_in', 0) // 86400} يوماً — أعد تشغيل هذا السكربت قبل انتهائها.")
    print("ادفع content/token_dates.json إلى المستودع ليعرف فحص الصحة تاريخ الإصدار.")


if __name__ == "__main__":
    main()
