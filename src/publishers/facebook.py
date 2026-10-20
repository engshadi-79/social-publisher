import json
import os

import requests

from config import GRAPH_VERSION

from .base import Publisher, PublishError, check, creds_for


class Facebook(Publisher):
    name = "facebook"

    def publish(self, post, text, image_path, image_url, acct=None):
        c = creds_for("facebook", acct)
        page, tok = c["page_id"], c["token"]
        base = f"https://graph.facebook.com/{GRAPH_VERSION}/{page}"
        urls = post.get("_urls") or []
        if post["template"] == "reel":
            d = check(requests.post(f"{base}/videos", timeout=300,
                                    data={"file_url": image_url, "description": text,
                                          "access_token": tok}), "facebook videos")
            return str(d.get("post_id") or d["id"])
        if post["template"] == "carousel" and len(urls) >= 2:
            # ألبوم: ارفع كل صورة غير منشورة ثم أنشئ منشوراً واحداً يرفقها كلها
            data = {"message": text, "access_token": tok}
            for i, u in enumerate(urls):
                pid = check(requests.post(f"{base}/photos", timeout=60,
                                          data={"url": u, "published": "false", "access_token": tok}),
                            f"facebook photo {i + 1}")["id"]
                data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
            d = check(requests.post(f"{base}/feed", timeout=60, data=data), "facebook feed")
            return str(d["id"])
        r = requests.post(f"{base}/photos", timeout=60,
                          data={"url": image_url, "message": text, "access_token": tok})
        d = check(r, "facebook photos")
        return str(d.get("post_id") or d["id"])
