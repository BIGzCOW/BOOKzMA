#!/usr/bin/env python3
"""Update .kilo/progress.json after completing a task.

Usage:
    python scripts/update_progress.py --task <task_id> --status <done|in_progress|blocked>
    python scripts/update_progress.py --task <task_id> --status done --note "<note>"
    python scripts/update_progress.py --task <task_id> --status blocked --blocker "<reason>"
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

PROGRESS_FILE = Path(__file__).resolve().parent.parent / ".kilo" / "progress.json"


def load() -> dict:
    if not PROGRESS_FILE.exists():
        return {
            "session_id": "",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": "",
            "current_phase": "",
            "current_task": "",
            "completed_tasks": [],
            "in_progress_tasks": [],
            "pending_tasks": [],
            "notes": "",
            "blockers": [],
        }
    return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))


def save(data: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update .kilo/progress.json")
    parser.add_argument("--task", required=True, help="Task ID (e.g. Task 2.1)")
    parser.add_argument(
        "--status",
        required=True,
        choices=["done", "in_progress", "blocked"],
        help="New status for the task",
    )
    parser.add_argument("--note", default="", help="Optional note to append")
    parser.add_argument("--blocker", default="", help="Optional blocker reason")
    args = parser.parse_args()

    data = load()
    now = datetime.now(timezone.utc).isoformat()
    data["updated_at"] = now
    if not data.get("started_at"):
        data["started_at"] = now
    data["current_task"] = args.task

    task_lists = {
        "done": ("completed_tasks", "in_progress_tasks", "pending_tasks"),
        "in_progress": ("in_progress_tasks", "pending_tasks", "completed_tasks"),
        "blocked": ("in_progress_tasks", "pending_tasks", "completed_tasks"),
    }
    add_to, remove_from_1, remove_from_2 = task_lists[args.status]

    for lst_name in (remove_from_1, remove_from_2):
        data[lst_name] = [t for t in data.get(lst_name, []) if t != args.task]

    if args.task not in data.get(add_to, []):
        data.setdefault(add_to, []).append(args.task)

    data["current_phase"] = args.task.split()[0] if " " in args.task else "Phase 2"

    if args.note:
        data["notes"] = (data.get("notes", "") + " | " + args.note).strip(" |")
    if args.blocker:
        if args.blocker not in data.get("blockers", []):
            data.setdefault("blockers", []).append(args.blocker)

    save(data)
    print(f"Updated {PROGRESS_FILE}: {args.task} -> {args.status}")


if __name__ == "__main__":
    main()
