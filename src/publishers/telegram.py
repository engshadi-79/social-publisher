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
        with open(image_path, "rb") as f:
            r = requests.post(f"{api}/sendPhoto", data={"chat_id": chat, **({"caption": text} if short else {})},
                              files={"photo": f}, timeout=60)
        msg = check(r, "telegram sendPhoto")["result"]
        if not short:
            r2 = requests.post(f"{api}/sendMessage", timeout=30, json={
                "chat_id": chat, "text": text, "reply_to_message_id": msg["message_id"]})
            check(r2, "telegram sendMessage")
        return str(msg["message_id"])
