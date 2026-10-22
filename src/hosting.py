"""رفع الصور واللوحة إلى فرع gh-pages وإرجاع روابط HTTPS عامة."""
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from config import ROOT

BOT = ["-c", "user.name=publisher-bot", "-c", "user.email=publisher-bot@users.noreply.github.com"]


def _git(*args, cwd=ROOT, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def public_url(name: str) -> str:
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/")
    return f"https://{owner}.github.io/{repo}/{name}"


def _push_to_pages(copy, message: str) -> None:
    """ينسخ الملفات داخل نسخة عمل من gh-pages عبر copy(root) ثم يدفعها."""
    if "GITHUB_REPOSITORY" not in os.environ:
        raise RuntimeError("GITHUB_REPOSITORY غير مضبوط — الاستضافة تعمل داخل GitHub Actions فقط")
    tmp = Path(tempfile.mkdtemp(prefix="ghpages-"))
    exists = _git("ls-remote", "--exit-code", "--heads", "origin", "gh-pages", check=False).returncode == 0
    try:
        if exists:
            _git("fetch", "origin", "gh-pages")
            _git("worktree", "add", "-f", str(tmp), "origin/gh-pages", "--detach")
        else:
            _git("worktree", "add", "-f", "--detach", str(tmp))
            _git("checkout", "--orphan", "gh-pages", cwd=tmp)
            _git("rm", "-rf", ".", cwd=tmp, check=False)
        (tmp / "images").mkdir(exist_ok=True)
        (tmp / ".nojekyll").touch()
        copy(tmp)
        _git("add", "-A", cwd=tmp)
        if _git("status", "--porcelain", cwd=tmp).stdout.strip():
            _git(*BOT, "commit", "-m", message, cwd=tmp)
            _git("push", "origin", "HEAD:refs/heads/gh-pages", cwd=tmp)
    finally:
        _git("worktree", "remove", "--force", str(tmp), check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def upload(files: list[Path]) -> dict[str, str]:
    """يرفع الملفات إلى gh-pages/images ويرجع {اسم الملف: الرابط}."""
    def copy(root: Path):
        for f in files:
            shutil.copy2(f, root / "images" / f.name)

    _push_to_pages(copy, "images [skip ci]")
    urls = {f.name: public_url(f"images/{f.name}") for f in files}
    for url in urls.values():
        _wait(url)
    return urls


def upload_site(src: Path, with_images: bool = True) -> str:
    """ينسخ محتويات مجلد (index.html و images/) إلى جذر gh-pages دون حذف صور المنشورات."""
    def copy(root: Path):
        shutil.copy2(src / "index.html", root / "index.html")
        for stale in list((root / "images").glob("full-*")) + list((root / "images").glob("thumb-*")):
            stale.unlink()                      # معاينات اللوحة تُبنى من جديد كل مرة، فلا تبقى قديمة أو بأسماء مكشوفة
        for f in (src / "images").glob("*") if with_images else []:
            shutil.copy2(f, root / "images" / f.name)

    _push_to_pages(copy, "dashboard [skip ci]")
    return public_url("")


def _wait(url: str, timeout: int = 300) -> None:
    """GitHub Pages يحتاج دقائق بعد الدفع؛ ننتظر حتى يصبح الرابط متاحاً."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if requests.head(url, timeout=15).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(10)
    raise RuntimeError(f"الرابط لم يصبح متاحاً خلال {timeout} ثانية: {url}")
