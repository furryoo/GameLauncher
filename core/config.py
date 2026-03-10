import os
import yaml
from dataclasses import dataclass, field, asdict
from typing import List

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


@dataclass
class TaskConfig:
    name: str = ""
    exe_path: str = ""
    process_name: str = ""
    timeout: int = 0  # 0 = no limit, seconds
    enabled: bool = True


@dataclass
class ScheduleConfig:
    enabled: bool = False
    time: str = "22:00"


@dataclass
class AppConfig:
    tasks: List[TaskConfig] = field(default_factory=list)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)


def load_config() -> AppConfig:
    if not os.path.exists(CONFIG_PATH):
        return AppConfig()
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tasks = [TaskConfig(**t) for t in data.get("tasks", [])]
    sched_data = data.get("schedule", {})
    schedule = ScheduleConfig(**sched_data)
    return AppConfig(tasks=tasks, schedule=schedule)


def save_config(config: AppConfig):
    data = {
        "tasks": [asdict(t) for t in config.tasks],
        "schedule": asdict(config.schedule),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
