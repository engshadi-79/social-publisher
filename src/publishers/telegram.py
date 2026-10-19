import json
import os

import requests

from .base import Publisher, PublishError, check


class Telegram(Publisher):
    name = "telegram"
    needs_url = False

    def publish(self, post, text, image_path, image_url):
        tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
        if not (tok and chat):
            raise PublishError("TELEGRAM_BOT_TOKEN/TELEGRAM_CHANNEL_ID غير مضبوطين")
        api = f"https://api.telegram.org/bot{tok}"
        short = len(text) <= 1024
        files = post.get("_files") or []
        if post["template"] == "carousel" and len(files) >= 2:
            media, handles = [], {}
            try:
                for i, f in enumerate(files[:10]):             # الحد الأقصى في ألبوم تيليجرام 10
                    item = {"type": "photo", "media": f"attach://p{i}"}
                    if i == 0 and short:
                        item["caption"] = text
                    media.append(item)
                    handles[f"p{i}"] = open(f, "rb")
                r = requests.post(f"{api}/sendMediaGroup", data={"chat_id": chat, "media": json.dumps(media)},
                                  files=handles, timeout=120)
            finally:
                for h in handles.values():
                    h.close()
            first = check(r, "telegram sendMediaGroup")["result"][0]
        else:
            with open(image_path, "rb") as f:
                r = requests.post(f"{api}/sendPhoto", data={"chat_id": chat, **({"caption": text} if short else {})},
                                  files={"photo": f}, timeout=60)
            first = check(r, "telegram sendPhoto")["result"]
        if not short:
            r2 = requests.post(f"{api}/sendMessage", timeout=30, json={
                "chat_id": chat, "text": text, "reply_to_message_id": first["message_id"]})
            check(r2, "telegram sendMessage")
        return str(first["message_id"])
