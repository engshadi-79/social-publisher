from pathlib import Path


class PublishError(Exception):
    pass


class Publisher:
    name = ""
    needs_url = True          # هل يحتاج رابط صورة عاماً؟

    def publish(self, post: dict, text: str, image_path: Path, image_url: str | None) -> str:
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
