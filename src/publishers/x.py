"""النشر على X (تويتر سابقاً) عبر واجهة v2 بتوثيق OAuth 1.0a.

OAuth 1.0a لا تنتهي صلاحيته، فلا يحتاج تجديداً أسبوعياً مثل ثريدز.
الصور تُرفع من الملف مباشرة، فلا حاجة لاستضافة رابط عام.
"""
from pathlib import Path

import requests
from requests_oauthlib import OAuth1

from .base import Publisher, PublishError, creds_for

API = "https://api.x.com/2"
UPLOAD_V1 = "https://upload.twitter.com/1.1/media/upload.json"
MAX_MEDIA = 4                      # الحد الأقصى لصور المنشور الواحد على X


def _auth(c: dict) -> OAuth1:
    return OAuth1(c["api_key"], c["api_secret"], c["access_token"], c["access_secret"])


def _fail(resp, what: str):
    """رسالة خطأ واضحة: ردّ X قد يكون {errors:[...]} أو {detail:...} أو نصاً."""
    try:
        d = resp.json()
    except Exception:  # noqa: BLE001
        d = {}
    msg = ""
    if isinstance(d, dict):
        errs = d.get("errors")
        if isinstance(errs, list) and errs:
            msg = "; ".join(str(e.get("message") or e.get("detail") or e) for e in errs)
        msg = msg or str(d.get("detail") or d.get("title") or "")
    raise PublishError(f"{what}: HTTP {resp.status_code} {(msg or resp.text)[:300]}")


def _upload_v1(auth: OAuth1, data: bytes) -> str:
    r = requests.post(UPLOAD_V1, auth=auth, files={"media": data}, timeout=120)
    if r.status_code >= 400:
        _fail(r, "x media upload (v1.1)")
    mid = r.json().get("media_id_string")
    if not mid:
        raise PublishError("x media upload (v1.1): لا media_id في الرد")
    return str(mid)


def _upload_v2(auth: OAuth1, data: bytes) -> str:
    """الرفع المجزّأ في v2: تهيئة ثم إرسال ثم إنهاء."""
    r = requests.post(f"{API}/media/upload/initialize", auth=auth, timeout=60,
                      json={"media_type": "image/png", "total_bytes": len(data),
                            "media_category": "tweet_image"})
    if r.status_code >= 400:
        _fail(r, "x media initialize")
    mid = str((r.json().get("data") or {}).get("id") or "")
    if not mid:
        raise PublishError("x media initialize: لا معرّف في الرد")
    r = requests.post(f"{API}/media/upload/{mid}/append", auth=auth, timeout=180,
                      data={"segment_index": 0}, files={"media": data})
    if r.status_code >= 400:
        _fail(r, "x media append")
    r = requests.post(f"{API}/media/upload/{mid}/finalize", auth=auth, timeout=120)
    if r.status_code >= 400:
        _fail(r, "x media finalize")
    return mid


def _upload(auth: OAuth1, path: Path) -> str:
    """يجرّب مسارَي الرفع: ما زال المتاح منهما يختلف بين الحسابات ومستويات الوصول."""
    data = path.read_bytes()
    try:
        return _upload_v1(auth, data)
    except PublishError as first:
        try:
            return _upload_v2(auth, data)
        except PublishError as second:
            raise PublishError(f"تعذّر رفع الصورة إلى X — v1.1: {first} | v2: {second}") from second


class X(Publisher):
    name = "x"
    needs_url = False              # الصور تُرفع من الملف، لا من رابط عام

    def publish(self, post, text, image_path, image_url, acct=None):
        c = creds_for("x", acct)
        auth = _auth(c)
        files = post.get("_files") or [image_path]
        media = [_upload(auth, Path(f)) for f in files[:MAX_MEDIA]]
        body = {"text": text, "media": {"media_ids": media}}
        r = requests.post(f"{API}/tweets", auth=auth, json=body, timeout=60)
        if r.status_code == 404:                      # الاسم الجديد للمسار نفسه
            r = requests.post(f"{API}/posts", auth=auth, json=body, timeout=60)
        if r.status_code >= 400:
            _fail(r, "x create post")
        pid = str((r.json().get("data") or {}).get("id") or "")
        if not pid:
            raise PublishError("x create post: لا معرّف منشور في الرد")
        return pid
