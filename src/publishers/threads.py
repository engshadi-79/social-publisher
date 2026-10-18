import os
import time

import requests

from config import THREADS_VERSION

from .base import Publisher, PublishError, check

BASE = f"https://graph.threads.net/{THREADS_VERSION}"


class Threads(Publisher):
    name = "threads"

    def publish(self, post, text, image_path, image_url):
        uid, tok = os.environ.get("THREADS_USER_ID"), os.environ.get("THREADS_TOKEN")
        if not (uid and tok):
            raise PublishError("THREADS_USER_ID/THREADS_TOKEN غير مضبوطين")
        cid = check(requests.post(f"{BASE}/{uid}/threads", timeout=60, data={
            "media_type": "IMAGE", "image_url": image_url, "text": text, "access_token": tok}),
            "threads create")["id"]
        for _ in range(30):
            st = check(requests.get(f"{BASE}/{cid}", timeout=30,
                                    params={"fields": "status,error_message", "access_token": tok}),
                       "threads status")
            if st.get("status") == "FINISHED":
                break
            if st.get("status") in ("ERROR", "EXPIRED"):
                raise PublishError(f"threads container {st['status']}: {st.get('error_message')}")
            time.sleep(4)
        else:
            raise PublishError("threads: انتهت مهلة المعالجة")
        pub = check(requests.post(f"{BASE}/{uid}/threads_publish", timeout=60,
                                  data={"creation_id": cid, "access_token": tok}), "threads publish")
        return str(pub["id"])
