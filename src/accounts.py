"""الحسابات/الصفحات المستهدفة بالنشر، وقراءة أسرارها (مباشرة من البيئة أو من ALL_SECRETS)."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from config import PLATFORMS, ROOT

ACCOUNTS_PATH = Path(os.environ.get("ACCOUNTS_FILE") or ROOT / "content" / "accounts.yaml")


@dataclass
class Account:
    id: str
    platform: str
    label: str
    default: bool
    secrets: dict

    def creds(self) -> dict:
        """يحوّل أسماء الأسرار إلى قيمها (مع الاحتياط fallback_*). القيم الفارغة تُحذف."""
        out = {}
        for role, name in self.secrets.items():
            if role.startswith("fallback_"):
                continue
            v = secret(name) or secret(self.secrets.get("fallback_" + role, ""))
            if v:
                out[role] = v
        return out


_all_cache = None


def secret(name: str) -> str:
    if not name:
        return ""
    v = os.environ.get(name)
    if v:
        return v
    global _all_cache
    if _all_cache is None:
        try:
            _all_cache = json.loads(os.environ.get("ALL_SECRETS", "") or "{}")
        except Exception:  # noqa: BLE001
            _all_cache = {}
    return str(_all_cache.get(name, "") or "")


def secret_values() -> list[str]:
    """كل قيم الأسرار المعروفة (لإخفائها من رسائل الخطأ)."""
    secret("-")                                   # يضمن تحميل ALL_SECRETS
    vals = {v for v in (_all_cache or {}).values() if isinstance(v, str) and len(v) > 8}
    return sorted(vals, key=len, reverse=True)


def load_accounts() -> dict[str, Account]:
    data = yaml.safe_load(ACCOUNTS_PATH.read_text(encoding="utf-8")) if ACCOUNTS_PATH.exists() else {}
    out = {}
    for a in (data or {}).get("accounts") or []:
        if isinstance(a, dict) and a.get("id") and a.get("platform") in PLATFORMS:
            out[str(a["id"])] = Account(str(a["id"]), a["platform"], str(a.get("label") or a["id"]),
                                        bool(a.get("default")), a.get("secrets") or {})
    return out


def defaults(accounts: dict[str, Account] | None = None) -> dict[str, list[Account]]:
    accounts = accounts or load_accounts()
    out: dict[str, list[Account]] = {p: [] for p in PLATFORMS}
    for a in accounts.values():
        if a.default:
            out[a.platform].append(a)
    return out


def state_key(platform: str, acct: Account) -> str:
    """مفتاح الحالة: اسم المنصة للحساب الافتراضي (توافقاً مع الحالة القديمة)، وإلا «منصة:معرّف»."""
    return platform if acct.default else f"{platform}:{acct.id}"


@dataclass
class Target:
    platform: str
    account: Account
    key: str


def targets_of(post: dict, accounts: dict[str, Account] | None = None) -> list[Target]:
    """أهداف النشر لمنشور: لكل منصة فيه نص، الحسابات المحددة في targets أو الافتراضية."""
    accounts = accounts or load_accounts()
    dfl = defaults(accounts)
    chosen = post.get("targets") or {}
    out = []
    for platform in post.get("platforms", {}):
        ids = chosen.get(platform)
        accts = [accounts[i] for i in ids if i in accounts and accounts[i].platform == platform] if ids else dfl.get(platform, [])
        for a in accts:
            out.append(Target(platform, a, state_key(platform, a)))
    return out
