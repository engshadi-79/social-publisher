import os
import time

import requests

from config import GRAPH_VERSION

from .base import Publisher, PublishError, check


class Instagram(Publisher):
    name = "instagram"

    def publish(self, post, text, image_path, image_url):
        uid, tok = os.environ.get("IG_USER_ID"), os.environ.get("FB_PAGE_TOKEN")
        if not (uid and tok):
            raise PublishError("IG_USER_ID/FB_PAGE_TOKEN غير مضبوطين")
        base = f"https://graph.facebook.com/{GRAPH_VERSION}"
        data = {"image_url": image_url, "access_token": tok}
        if post["template"] == "story":      # 9:16 لا يصلح منشوراً عادياً
            data["media_type"] = "STORIES"
        else:
            data["caption"] = text
        cid = check(requests.post(f"{base}/{uid}/media", data=data, timeout=60), "instagram media")["id"]
        for _ in range(30):
            st = check(requests.get(f"{base}/{cid}", timeout=30,
                                    params={"fields": "status_code,status", "access_token": tok}),
                       "instagram status")
            code = st.get("status_code")
            if code == "FINISHED":
                break
            if code in ("ERROR", "EXPIRED"):
                raise PublishError(f"instagram container {code}: {st.get('status')}")
            time.sleep(4)
        else:
            raise PublishError("instagram: انتهت مهلة معالجة الصورة")
        pub = check(requests.post(f"{base}/{uid}/media_publish", timeout=60,
                                  data={"creation_id": cid, "access_token": tok}), "instagram publish")
        return str(pub["id"])
