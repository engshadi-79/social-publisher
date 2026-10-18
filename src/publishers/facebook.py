import os

import requests

from config import GRAPH_VERSION

from .base import Publisher, PublishError, check


class Facebook(Publisher):
    name = "facebook"

    def publish(self, post, text, image_path, image_url):
        page, tok = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_PAGE_TOKEN")
        if not (page and tok):
            raise PublishError("FB_PAGE_ID/FB_PAGE_TOKEN غير مضبوطين")
        r = requests.post(f"https://graph.facebook.com/{GRAPH_VERSION}/{page}/photos", timeout=60,
                          data={"url": image_url, "message": text, "access_token": tok})
        d = check(r, "facebook photos")
        return str(d.get("post_id") or d["id"])
