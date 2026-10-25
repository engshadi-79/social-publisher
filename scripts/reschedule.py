"""يعيد جدولة المنشورات التي لم تُنشر بعد على أوقات الذروة (3 يومياً) بترتيب مواعيدها الحالي.

    python scripts/reschedule.py          # يعرض الخطة فقط
    python scripts/reschedule.py --apply  # يكتبها في content/queue.yaml

لا يمسّ ما نُشر على أي منصة. يعدّل أسطر publish_at فقط فيبقى تنسيق الملف كما هو.
"""
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from config import QUEUE_PATH, STATE_PATH  # noqa: E402
from generate import MORNING_SLOT, REEL_SLOT, SLOTS  # noqa: E402
from queue_io import load_queue, now_local, parse_when  # noqa: E402


def main() -> int:
    apply = "--apply" in sys.argv
    queue = load_queue()
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    pending = [p for p in queue if not any(v.get("status") == "published" for v in state.get(p["id"], {}).values())
               and str(p["publish_at"])[11:16] not in (REEL_SLOT, MORNING_SLOT)]   # الريلات لها مواعيد ثابتة
    pending.sort(key=lambda p: (not p["approved"], parse_when(p["publish_at"])))   # المعتمد أولاً
    now = now_local()
    plan: dict[str, str] = {}
    day, k = now.date(), 0
    for p in pending:
        while True:
            slot = SLOTS[k % len(SLOTS)]
            when = f"{day:%Y-%m-%d} {slot}"
            if parse_when(when) > now + timedelta(minutes=45):
                break
            k += 1
            if k % len(SLOTS) == 0:
                day += timedelta(days=1)
        plan[p["id"]] = when
        k += 1
        if k % len(SLOTS) == 0:
            day += timedelta(days=1)
    for pid, when in plan.items():
        print(f"{pid}  ->  {when}")
    if not apply:
        return 0
    text = QUEUE_PATH.read_text(encoding="utf-8")
    lines = text.split("\n")
    cur = None
    for i, line in enumerate(lines):
        m = re.match(r'^- id:\s*"?([^"\s]+)"?\s*$', line)
        if m:
            cur = m.group(1)
        elif cur in plan and re.match(r"^  publish_at:", line):
            lines[i] = f'  publish_at: "{plan[cur]}"'
            cur = None
    QUEUE_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"عُدّلت {len(plan)} مواعيد")
    return 0


if __name__ == "__main__":
    sys.exit(main())
