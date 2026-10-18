"""رسالة ملخّص إلى محادثة المالك الخاصة على تيليجرام."""
import os

import requests


def send(text: str) -> bool:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if not (tok and chat):
        print("[notify] لا إعداد للإشعار — الرسالة:\n" + text)
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=30,
                          json={"chat_id": chat, "text": text[:4000]})
        return r.ok
    except requests.RequestException as e:
        print(f"[notify] فشل الإرسال: {type(e).__name__}")
        return False
