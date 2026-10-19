import os
import time

import requests

from config import GRAPH_VERSION

from .base import Publisher, PublishError, check


def _wait_finished(base: str, cid: str, tok: str, what: str):
    for _ in range(30):
        st = check(requests.get(f"{base}/{cid}", timeout=30,
                                params={"fields": "status_code,status", "access_token": tok}),
                   f"instagram status ({what})")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"instagram container {code}: {st.get('status')}")
        time.sleep(4)
    raise PublishError(f"instagram: انتهت مهلة معالجة {what}")


class Instagram(Publisher):
    name = "instagram"

    def publish(self, post, text, image_path, image_url):
        uid, tok = os.environ.get("IG_USER_ID"), os.environ.get("FB_PAGE_TOKEN")
        if not (uid and tok):
            raise PublishError("IG_USER_ID/FB_PAGE_TOKEN غير مضبوطين")
        base = f"https://graph.facebook.com/{GRAPH_VERSION}"
        urls = post.get("_urls") or []
        if post["template"] == "carousel" and len(urls) >= 2:
            kids = []
            for i, u in enumerate(urls[:10], 1):               # الحد الأقصى في إنستغرام 10
                cid = check(requests.post(f"{base}/{uid}/media", timeout=60, data={
                    "image_url": u, "is_carousel_item": "true", "access_token": tok}), f"instagram item {i}")["id"]
                _wait_finished(base, cid, tok, f"الشريحة {i}")
                kids.append(cid)
            data = {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": text, "access_token": tok}
        else:
            data = {"image_url": image_url, "access_token": tok}
            if post["template"] == "story":      # 9:16 لا يصلح منشوراً عادياً
                data["media_type"] = "STORIES"
            else:
                data["caption"] = text
        cid = check(requests.post(f"{base}/{uid}/media", data=data, timeout=60), "instagram media")["id"]
        _wait_finished(base, cid, tok, "المنشور")
        pub = check(requests.post(f"{base}/{uid}/media_publish", timeout=60,
                                  data={"creation_id": cid, "access_token": tok}), "instagram publish")
        return str(pub["id"])
