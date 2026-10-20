"""النشر على لينكدإن عبر منتج «Share on LinkedIn» (مجاني وذاتي الخدمة، بلا مراجعة شراكة).

المسار الرسمي للمنتج: تسجيل الصورة في assets ثم رفعها ثم إنشاء المنشور في ugcPosts.
لم أستعمل واجهة /rest/posts الأحدث عمداً: حقل commentary فيها يوجب تهريب رموز
منها # و( ) و_ بخط مائل عكسي، وهذا يُفسد الهاشتاجات العربية في نصوصنا.

التوكن يعيش 60 يوماً، والتجديد البرمجي مقصور على شركاء MDP المعتمدين،
فعلى صاحب الحساب إعادة التفويض يدوياً: python scripts/setup_linkedin.py
"""
from pathlib import Path

import requests

from .base import Publisher, PublishError, creds_for

API = "https://api.linkedin.com/v2"
MAX_MEDIA = 9                      # أقصى ما يقبله منشور الصور المتعددة على لينكدإن


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-Restli-Protocol-Version": "2.0.0"}


def _fail(resp, what: str):
    """رسالة خطأ واضحة: ردّ لينكدإن قد يكون {message:...} أو {errorDetails:...} أو نصاً."""
    try:
        d = resp.json()
    except Exception:  # noqa: BLE001
        d = {}
    msg = ""
    if isinstance(d, dict):
        msg = str(d.get("message") or d.get("error_description") or d.get("error") or "")
    raise PublishError(f"{what}: HTTP {resp.status_code} {(msg or resp.text)[:300]}")


def _upload(token: str, author: str, path: Path) -> str:
    """يسجّل الصورة ثم يرفع بايتاتها، ويرجع معرّف الأصل (asset URN)."""
    r = requests.post(f"{API}/assets?action=registerUpload", timeout=60, headers=_headers(token),
                      json={"registerUploadRequest": {
                          "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                          "owner": author,
                          "serviceRelationships": [{"relationshipType": "OWNER",
                                                    "identifier": "urn:li:userGeneratedContent"}]}})
    if r.status_code >= 400:
        _fail(r, "linkedin registerUpload")
    value = (r.json() or {}).get("value") or {}
    asset = value.get("asset")
    try:
        url = value["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    except (KeyError, TypeError):
        raise PublishError("linkedin registerUpload: لا رابط رفع في الرد") from None
    if not asset:
        raise PublishError("linkedin registerUpload: لا معرّف أصل في الرد")
    up = requests.put(url, data=path.read_bytes(), timeout=180,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"})
    if up.status_code >= 400:
        _fail(up, "linkedin رفع الصورة")
    return str(asset)


class LinkedIn(Publisher):
    name = "linkedin"
    needs_url = False              # الصور تُرفع من الملف، لا من رابط عام

    def publish(self, post, text, image_path, image_url, acct=None):
        c = creds_for("linkedin", acct)
        token, author = c["token"], c["author_urn"]
        files = post.get("_files") or [image_path]
        media = [{"status": "READY", "media": _upload(token, author, Path(f))}
                 for f in files[:MAX_MEDIA]]
        body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "IMAGE",
                "media": media,
            }},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        r = requests.post(f"{API}/ugcPosts", timeout=90,
                          headers={**_headers(token), "Content-Type": "application/json"}, json=body)
        if r.status_code >= 400:
            _fail(r, "linkedin ugcPosts")
        # معرّف المنشور يأتي في ترويسة الرد لا في جسمه
        pid = r.headers.get("x-restli-id") or (r.json() or {}).get("id") or ""
        if not pid:
            raise PublishError("linkedin ugcPosts: لا معرّف منشور في الرد")
        return str(pid)
