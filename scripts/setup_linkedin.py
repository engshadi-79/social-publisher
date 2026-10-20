"""يحوّل كود تفويض لينكدإن إلى توكن (60 يوماً)، ويكتب LINKEDIN_TOKEN و LINKEDIN_AUTHOR_URN
في أسرار GitHub، ويسجّل تاريخ الإصدار ليُنبّهك فحص الصحة قبل انتهائه.
لا يطبع أي توكن ولا يحفظه في ملف.

الاستعمال:  python scripts/setup_linkedin.py --client-id <المعرّف>
يُعاد تشغيله كل 60 يوماً: التجديد البرمجي مقصور على شركاء MDP المعتمدين.

افتراضياً يلتقط رمز التفويض بنفسه عبر خادم محلي على المنفذ 8765، فلا تنسخ رابطاً.
يتطلّب ذلك تسجيل http://localhost:8765/callback في Authorized redirect URLs.
وإن تعذّر، استعمل --manual لتلصق الرابط يدوياً مع رابط صفحات GitHub.
"""
import argparse
import getpass
import json
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

REPO = "engshadi-79/social-publisher"
LOCAL_PORT = 8765
LOCAL_REDIRECT = f"http://localhost:{LOCAL_PORT}/callback"
PAGES_REDIRECT = "https://engshadi-79.github.io/social-publisher/"
SCOPES = "openid profile w_member_social"
DATES = Path(__file__).resolve().parent.parent / "content" / "token_dates.json"

DONE_PAGE = """<!doctype html><meta charset="utf-8">
<title>تم</title><style>body{font-family:system-ui,sans-serif;direction:rtl;text-align:center;
padding:80px 24px;background:#0B1F3A;color:#F5F1E8}h1{font-size:28px}p{opacity:.75}</style>
<h1>تمّ التفويض ✓</h1><p>أغلق هذه الصفحة وعُد إلى الطرفية.</p>"""


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


class _Catcher(BaseHTTPRequestHandler):
    """يلتقط ?code= من إعادة التوجيه ثم يُنهي الخادم."""

    result: dict = {}

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Catcher.result = {k: v[0] for k, v in q.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(DONE_PAGE.encode("utf-8"))

    def log_message(self, *a):  # صمتاً: لا نريد سجلّ HTTP في الطرفية
        pass


def wait_for_code(timeout=300) -> str:
    srv = HTTPServer(("localhost", LOCAL_PORT), _Catcher)
    srv.timeout = timeout
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    t.join(timeout)
    srv.server_close()
    res = _Catcher.result
    if res.get("error"):
        sys.exit(f"رفض التفويض: {res.get('error_description') or res['error']}")
    if not res.get("code"):
        sys.exit("لم يصل رمز التفويض خلال المهلة. أعد التشغيل، أو استعمل --manual.")
    return res["code"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", help="معرّف التطبيق العلني (من تبويب Auth)")
    ap.add_argument("--manual", action="store_true",
                    help="ألصق رابط إعادة التوجيه يدوياً بدل الالتقاط التلقائي")
    args = ap.parse_args()

    redirect = PAGES_REDIRECT if args.manual else LOCAL_REDIRECT
    client_id = args.client_id or input("LinkedIn Client ID: ").strip()
    print(f"\nرابط إعادة التوجيه المستعمل: {redirect}")
    print("(لا بدّ أن يكون مسجّلاً في Authorized redirect URLs داخل تبويب Auth.)\n")
    client_secret = getpass.getpass("ألصق Client Secret هنا ثم Enter (لن يظهر شيء وأنت تلصق): ").strip()
    if not client_secret:
        sys.exit("لم يصل أي سرّ.")

    url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect,
        "scope": SCOPES, "state": "shadi"})

    if args.manual:
        print("\nافتح هذا الرابط ووافق، ثم انسخ رابط الصفحة التي حُوّلت إليها كاملاً:")
        print(url + "\n")
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
        code = input("الرابط أو قيمة code: ").strip()
        if "code=" in code:
            code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query).get("code", [code])[0]
    else:
        print("افتح صفحة الموافقة واضغط «السماح». سألتقط الرمز بنفسي:")
        print(url + "\n")
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
        print("بانتظار الموافقة…")
        code = wait_for_code()
        print("وصل رمز التفويض ✓")

    tok = check(requests.post("https://www.linkedin.com/oauth/v2/accessToken", timeout=30, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
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
