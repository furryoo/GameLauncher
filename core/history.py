import json
import os
import datetime

from core.enums import RunResult

HISTORY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "history.json")
MAX_RECORDS = 500


def _load() -> list:
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(records: list):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(records[-MAX_RECORDS:], f, ensure_ascii=False, indent=2)


def add_record(task_name: str, status: RunResult, duration_seconds: int):
    """记录一次任务运行结果（最新记录在列表末尾）"""
    records = _load()
    records.append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "task": task_name,
        "status": str(status),
        "duration": duration_seconds,
    })
    _save(records)


def get_records() -> list:
    """返回最新在前的记录列表"""
    return _load()[::-1]


def get_task_stats() -> list[dict]:
    """按任务名聚合，返回 [{task, total, success, failed, avg_sec}] 按 total 降序"""
    from collections import defaultdict
    from core.enums import RunResult
    totals: dict[str, dict] = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0, "dur_sum": 0})
    for rec in _load():
        name = rec.get("task", "")
        if not name:
            continue
        entry = totals[name]
        entry["total"] += 1
        if rec.get("status") == RunResult.SUCCESS:
            entry["success"] += 1
        else:
            entry["failed"] += 1
        entry["dur_sum"] += rec.get("duration", 0)
    result = []
    for name, d in totals.items():
        result.append({
            "task": name,
            "total": d["total"],
            "success": d["success"],
            "failed": d["failed"],
            "avg_sec": d["dur_sum"] // d["total"] if d["total"] else 0,
        })
    result.sort(key=lambda x: x["total"], reverse=True)
    return result
