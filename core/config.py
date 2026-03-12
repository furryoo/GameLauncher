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
    timeout: int = 0        # 0 = no limit, seconds
    enabled: bool = True
    retry_count: int = 0    # 失败后重试次数 (0 = 不重试)
    delay_seconds: int = 0  # 启动前等待秒数


@dataclass
class ScheduleConfig:
    enabled: bool = False
    time: str = "22:00"
    post_action: str = PostAction.NONE
    days: List[int] = field(default_factory=lambda: list(range(7)))  # 0=周一…6=周日


@dataclass
class NotifyConfig:
    bark_url: str = ""  # Bark 推送 URL，空字符串表示不推送


@dataclass
class AppConfig:
    tasks: List[TaskConfig] = field(default_factory=list)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)


def _filter_fields(d: dict, cls) -> dict:
    """过滤字典，只保留 dataclass 中存在的字段（兼容旧版配置）"""
    valid = cls.__dataclass_fields__
    return {k: v for k, v in d.items() if k in valid}


def load_config() -> AppConfig:
    if not os.path.exists(CONFIG_PATH):
        return AppConfig()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tasks = [TaskConfig(**_filter_fields(t, TaskConfig)) for t in data.get("tasks", [])]
    schedule = ScheduleConfig(**_filter_fields(data.get("schedule", {}), ScheduleConfig))
    notify = NotifyConfig(**_filter_fields(data.get("notify", {}), NotifyConfig))
    return AppConfig(tasks=tasks, schedule=schedule, notify=notify)


def save_config(config: AppConfig):
    data = {
        "tasks": [asdict(t) for t in config.tasks],
        "schedule": asdict(config.schedule),
        "notify": asdict(config.notify),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
