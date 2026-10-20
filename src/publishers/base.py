from pathlib import Path


class PublishError(Exception):
    pass


REQUIRED = {"facebook": ("page_id", "token"), "instagram": ("user_id", "token"),
            "threads": ("user_id", "token"), "telegram": ("token", "chat_id")}


def creds_for(platform: str, acct=None) -> dict:
    """بيانات اعتماد الحساب المستهدف (الافتراضي للمنصة إن لم يُحدَّد)، مع خطأ واضح إن نقصت."""
    from accounts import defaults
    if acct is None:
        lst = defaults().get(platform) or []
        if not lst:
            raise PublishError(f"لا حساب افتراضي لمنصة {platform} في accounts.yaml")
        acct = lst[0]
    c = acct.creds()
    missing = [r for r in REQUIRED[platform] if not c.get(r)]
    if missing:
        raise PublishError(f"أسرار الحساب «{acct.label}» ناقصة: {', '.join(acct.secrets.get(r, r) for r in missing)}")
    return c


class Publisher:
    name = ""
    needs_url = True          # هل يحتاج رابط صورة عاماً؟

    def publish(self, post: dict, text: str, image_path: Path, image_url: str | None, acct=None) -> str:
        """ينشر ويرجع معرّف المنشور على المنصة، أو يرمي PublishError."""
        raise NotImplementedError


def check(resp, what: str):
    """يحوّل ردّ HTTP الفاشل إلى PublishError برسالة واضحة بلا أسرار."""
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        data = {}
    if resp.status_code >= 400 or (isinstance(data, dict) and "error" in data):
        err = data.get("error", data) if isinstance(data, dict) else data
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise PublishError(f"{what}: HTTP {resp.status_code} {str(msg or resp.text)[:300]}")
    return data
