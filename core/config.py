import os
import uuid
import yaml
from dataclasses import dataclass, field, asdict
from typing import List, Dict

from core.enums import PostAction, RunIf

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")


@dataclass
class TaskConfig:
    name: str = ""
    exe_path: str = ""
    timeout: int = 0        # 0 = no limit, seconds
    enabled: bool = True
    retry_count: int = 0    # 失败后重试次数 (0 = 不重试)
    delay_seconds: int = 0  # 启动前等待秒数
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    run_if: str = RunIf.ALWAYS   # "always" / "prev_success" / "prev_fail"
    notes: str = ""              # 备注（可选）


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
    profiles: Dict[str, List[TaskConfig]] = field(default_factory=lambda: {"默认": []})
    active_profile: str = "默认"
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)


def _filter_fields(d: dict, cls) -> dict:
    """过滤字典，只保留 dataclass 中存在的字段（兼容旧版配置）"""
    valid = cls.__dataclass_fields__
    return {k: v for k, v in d.items() if k in valid}


def _load_tasks(raw: list) -> List[TaskConfig]:
    return [TaskConfig(**_filter_fields(t, TaskConfig)) for t in (raw or [])]


def load_config() -> AppConfig:
    if not os.path.exists(CONFIG_PATH):
        return AppConfig()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        return AppConfig()

    # ── 加载 profiles（兼容旧版只有 tasks 的配置）─────────────────
    raw_profiles = data.get("profiles")
    old_tasks = data.get("tasks")
    if raw_profiles and isinstance(raw_profiles, dict):
        profiles = {name: _load_tasks(ptasks) for name, ptasks in raw_profiles.items()}
    elif old_tasks is not None:
        profiles = {"默认": _load_tasks(old_tasks)}
    else:
        profiles = {"默认": []}
    if not profiles:
        profiles = {"默认": []}

    active_profile = data.get("active_profile", "默认")
    if active_profile not in profiles:
        active_profile = next(iter(profiles))

    schedule = ScheduleConfig(**_filter_fields(data.get("schedule", {}), ScheduleConfig))
    notify = NotifyConfig(**_filter_fields(data.get("notify", {}), NotifyConfig))
    return AppConfig(profiles=profiles, active_profile=active_profile,
                     schedule=schedule, notify=notify)


def save_config(config: AppConfig):
    data = {
        "profiles": {
            name: [asdict(t) for t in tasks]
            for name, tasks in config.profiles.items()
        },
        "active_profile": config.active_profile,
        "schedule": asdict(config.schedule),
        "notify": asdict(config.notify),
    }
    tmp_path = CONFIG_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
    os.replace(tmp_path, CONFIG_PATH)
