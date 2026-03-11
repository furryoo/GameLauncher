import os
import yaml
from dataclasses import dataclass, field, asdict
from typing import List

from core.enums import PostAction

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


@dataclass
class TaskConfig:
    name: str = ""
    exe_path: str = ""
    process_name: str = ""
    timeout: int = 0        # 0 = no limit, seconds
    enabled: bool = True
    retry_count: int = 0    # 失败后重试次数 (0 = 不重试)
    delay_seconds: int = 0  # 启动前等待秒数


@dataclass
class ScheduleConfig:
    enabled: bool = False
    time: str = "22:00"
    post_action: str = PostAction.NONE  # 完成后操作


@dataclass
class AppConfig:
    tasks: List[TaskConfig] = field(default_factory=list)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)


def _task_from_dict(d: dict) -> TaskConfig:
    """兼容旧版配置：忽略未知字段"""
    valid = {f.name for f in TaskConfig.__dataclass_fields__.values()}
    return TaskConfig(**{k: v for k, v in d.items() if k in valid})


def load_config() -> AppConfig:
    if not os.path.exists(CONFIG_PATH):
        return AppConfig()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tasks = [_task_from_dict(t) for t in data.get("tasks", [])]
    sched_data = data.get("schedule", {})
    # 兼容旧版：过滤未知字段
    valid_sched = {f for f in ScheduleConfig.__dataclass_fields__}
    schedule = ScheduleConfig(**{k: v for k, v in sched_data.items() if k in valid_sched})
    return AppConfig(tasks=tasks, schedule=schedule)


def save_config(config: AppConfig):
    data = {
        "tasks": [asdict(t) for t in config.tasks],
        "schedule": asdict(config.schedule),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
