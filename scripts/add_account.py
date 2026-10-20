"""يضيف صفحة فيسبوك و/أو حساب إنستغرام جديداً إلى قائمة الحسابات التي يمكن اختيارها عند النشر.
يضبط الأسرار في GitHub ويُحدّث content/accounts.yaml في المستودع. لا يطبع أي توكن.

الاستعمال:  python scripts/add_account.py
المطلوب: توكن مستخدم قصير من Graph API Explorer يرى الصفحة المطلوبة (يُنسخ بأيقونة النسخ).
"""
import base64
import getpass
import json
import re
import subprocess
import sys

import requests

REPO = "engshadi-79/social-publisher"
V = "https://graph.facebook.com/v21.0"
ACC_PATH = "content/accounts.yaml"


def get(path, **params):
    r = requests.get(f"{V}/{path}", params=params, timeout=30)
    d = r.json()
    if r.status_code != 200 or "error" in d:
        sys.exit(f"خطأ من Meta: {d.get('error', {}).get('message', r.text[:200])}")
    return d


def gh(*args, stdin=None):
    p = subprocess.run(["gh", *args], input=stdin, text=True, capture_output=True)
    if p.returncode:
        sys.exit(f"فشل أمر gh: {p.stderr[:200]}")
    return p.stdout


def set_secret(name, value):
    gh("secret", "set", name, "-R", REPO, stdin=value)
    print(f"✓ {name}")


def yq(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def build_entries(page: dict, kinds: list[str]) -> tuple[list[str], dict[str, str]]:
    """يرجع (كتل YAML، الأسرار المطلوب ضبطها). الأسماء مشتقة من معرّف الصفحة فلا تتصادم."""
    slug = "P" + page["id"]
    secrets, blocks = {}, []
    if "facebook" in kinds:
        secrets[f"FB_{slug}_ID"], secrets[f"FB_{slug}_TOKEN"] = page["id"], page["access_token"]
        blocks.append(f"  - id: {yq('fb-' + page['id'])}\n    platform: facebook\n    label: {yq('فيسبوك — ' + page['name'])}\n"
                      f"    secrets: {{page_id: FB_{slug}_ID, token: FB_{slug}_TOKEN}}\n")
    if "instagram" in kinds:
        ig = page["instagram_business_account"]
        secrets[f"IG_{slug}_USER"], secrets[f"IG_{slug}_TOKEN"] = ig["id"], page["access_token"]
        blocks.append(f"  - id: {yq('ig-' + (ig.get('username') or ig['id']))}\n    platform: instagram\n    label: {yq('إنستغرام — ' + (ig.get('username') or ig['id']))}\n"
                      f"    secrets: {{user_id: IG_{slug}_USER, token: IG_{slug}_TOKEN}}\n")
    return blocks, secrets


def append_yaml(text: str, blocks: list[str]) -> str:
    """يضيف الكتل إلى آخر الملف (قائمة accounts هي آخر ما فيه) ويتجاهل ما هو موجود بنفس المعرّف."""
    out = text if text.endswith("\n") else text + "\n"
    for b in blocks:
        m = re.search(r"id: (\"[^\"]+\")", b)
        if m and m.group(1) in out or (m and m.group(1).strip('"') in out):
            print(f"تنبيه: الحساب {m.group(1)} موجود في accounts.yaml، تخطّيتُه.")
            continue
        out += b
    return out


WORKFLOWS = (".github/workflows/publish.yml", ".github/workflows/health.yml")
MARKER = "# ACCOUNT-SECRETS"


def add_env_lines(text: str, names) -> str:
    """يضيف سطر env لكل سرّ بعد علامة ACCOUNT-SECRETS (دون تكرار ما هو موجود)."""
    nl = chr(10)
    lines = text.split(nl)
    for i, l in enumerate(lines):
        if MARKER in l:
            indent = l[: len(l) - len(l.lstrip())]
            new = [indent + n + ": ${{ secrets." + n + " }}" for n in names if "secrets." + n + " }}" not in text]
            lines[i + 1:i + 1] = new
            return nl.join(lines)
    raise SystemExit("لم أجد العلامة " + MARKER + " في ملف الـ workflow.")


def update_workflows(names):
    for path in WORKFLOWS:
        cur = json.loads(gh("api", f"repos/{REPO}/contents/{path}"))
        text = base64.b64decode(cur["content"]).decode("utf-8")
        new = add_env_lines(text, names)
        if new != text:
            body = {"message": "workflows: expose secrets of a new account", "content": base64.b64encode(new.encode()).decode(), "sha": cur["sha"]}
            gh("api", "-X", "PUT", f"repos/{REPO}/contents/{path}", "--input", "-", stdin=json.dumps(body))
            print(f"✓ حُدّث {path}")


def main():
    app_id = input("App ID (تطبيق social-publisher): ").strip()
    app_secret = getpass.getpass("App Secret (مخفي): ").strip()
    short = getpass.getpass("التوكن القصير من Graph API Explorer (مخفي): ").strip()

    long_user = get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
                    client_secret=app_secret, fb_exchange_token=short)["access_token"]
    pages = get("me/accounts", access_token=long_user, limit=100,
                fields="id,name,access_token,instagram_business_account{id,username}").get("data", [])
    if not pages:
        sys.exit("لا توجد صفحات ضمن هذا التوكن.")
    for i, p in enumerate(pages):
        ig = p.get("instagram_business_account")
        print(f"[{i}] {p['name']}  ({'إنستغرام @' + str(ig.get('username', '?')) if ig else 'بلا إنستغرام'})")
    page = pages[int(input("رقم الصفحة: "))]
    has_ig = bool(page.get("instagram_business_account"))
    print("ماذا تضيف؟  1) فيسبوك   2) إنستغرام" + ("" if has_ig else " (غير متاح: لا حساب مربوط)") + "   3) الاثنان")
    ch = input("اختيارك: ").strip()
    kinds = {"1": ["facebook"], "2": ["instagram"], "3": ["facebook", "instagram"]}.get(ch)
    if not kinds or ("instagram" in kinds and not has_ig):
        sys.exit("اختيار غير صالح.")

    blocks, secrets = build_entries(page, kinds)
    for k, v in secrets.items():
        set_secret(k, v)

    cur = json.loads(gh("api", f"repos/{REPO}/contents/{ACC_PATH}"))
    text = base64.b64decode(cur["content"]).decode("utf-8")
    new_text = append_yaml(text, blocks)
    if new_text != text:
        body = {"message": "accounts: add " + page["name"], "content": base64.b64encode(new_text.encode()).decode(), "sha": cur["sha"]}
        gh("api", "-X", "PUT", f"repos/{REPO}/contents/{ACC_PATH}", "--input", "-", stdin=json.dumps(body))
        print("✓ تم تحديث content/accounts.yaml")
    update_workflows(list(secrets))
    print("تم. الحسابات الجديدة تظهر في اللوحة عند اختيار «على أي حساب؟» (خلال دقائق).")


if __name__ == "__main__":
    main()
