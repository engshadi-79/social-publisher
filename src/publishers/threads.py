import os
import time

import requests

from config import THREADS_VERSION

from .base import Publisher, PublishError, check

BASE = f"https://graph.threads.net/{THREADS_VERSION}"


def _wait_finished(cid: str, tok: str, what: str):
    for _ in range(30):
        st = check(requests.get(f"{BASE}/{cid}", timeout=30,
                                params={"fields": "status,error_message", "access_token": tok}),
                   f"threads status ({what})")
        if st.get("status") == "FINISHED":
            return
        if st.get("status") in ("ERROR", "EXPIRED"):
            raise PublishError(f"threads container {st['status']}: {st.get('error_message')}")
        time.sleep(4)
    raise PublishError(f"threads: انتهت مهلة معالجة {what}")


class Threads(Publisher):
    name = "threads"

    def publish(self, post, text, image_path, image_url):
        uid, tok = os.environ.get("THREADS_USER_ID"), os.environ.get("THREADS_TOKEN")
        if not (uid and tok):
            raise PublishError("THREADS_USER_ID/THREADS_TOKEN غير مضبوطين")
        urls = post.get("_urls") or []
        if post["template"] == "carousel" and len(urls) >= 2:
            kids = []
            for i, u in enumerate(urls[:20], 1):
                cid = check(requests.post(f"{BASE}/{uid}/threads", timeout=60, data={
                    "media_type": "IMAGE", "image_url": u, "is_carousel_item": "true", "access_token": tok}),
                    f"threads item {i}")["id"]
                _wait_finished(cid, tok, f"الشريحة {i}")
                kids.append(cid)
            data = {"media_type": "CAROUSEL", "children": ",".join(kids), "text": text, "access_token": tok}
        else:
            data = {"media_type": "IMAGE", "image_url": image_url, "text": text, "access_token": tok}
        cid = check(requests.post(f"{BASE}/{uid}/threads", timeout=60, data=data), "threads create")["id"]
        _wait_finished(cid, tok, "المنشور")
        pub = check(requests.post(f"{BASE}/{uid}/threads_publish", timeout=60,
                                  data={"creation_id": cid, "access_token": tok}), "threads publish")
        return str(pub["id"])
