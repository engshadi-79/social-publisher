"""رفع الصور إلى فرع gh-pages وإرجاع روابط HTTPS عامة."""
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from config import ROOT


def _git(*args, cwd=ROOT, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def public_url(name: str) -> str:
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/")
    return f"https://{owner}.github.io/{repo}/images/{name}"


def upload(files: list[Path]) -> dict[str, str]:
    """يرفع الملفات إلى gh-pages/images ويرجع {اسم الملف: الرابط}. يتطلب GITHUB_REPOSITORY."""
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
        for f in files:
            shutil.copy2(f, tmp / "images" / f.name)
        _git("add", "-A", cwd=tmp)
        if _git("status", "--porcelain", cwd=tmp).stdout.strip():
            _git("commit", "-m", "images [skip ci]", cwd=tmp)
            _git("push", "origin", "HEAD:refs/heads/gh-pages", cwd=tmp)
    finally:
        _git("worktree", "remove", "--force", str(tmp), check=False)
        shutil.rmtree(tmp, ignore_errors=True)
    urls = {f.name: public_url(f.name) for f in files}
    for url in urls.values():
        _wait(url)
    return urls


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
