import json
import os
import datetime
from collections import defaultdict

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
    tmp_path = HISTORY_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(records[-MAX_RECORDS:], f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, HISTORY_PATH)


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


def _compute_stats(records: list) -> list[dict]:
    totals: dict[str, dict] = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0, "dur_sum": 0})
    for rec in records:
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


def get_task_stats() -> list[dict]:
    """按任务名聚合，返回 [{task, total, success, failed, avg_sec}] 按 total 降序"""
    return _compute_stats(_load())


def get_records_and_stats() -> tuple[list, list[dict]]:
    """一次加载，返回 (records_newest_first, stats)"""
    raw = _load()
    return raw[::-1], _compute_stats(raw)
