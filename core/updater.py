import json
import os
import subprocess
import sys
import urllib.request
from PySide6.QtCore import QThread, Signal

REPO = "furryoo/GameLauncher"
_ROOT = os.path.dirname(os.path.dirname(__file__))


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def current_version() -> str:
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, cwd=_ROOT,
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


class UpdateWorker(QThread):
    status = Signal(str)          # 进度文字
    versions_ready = Signal(list) # 版本列表
    done = Signal(bool, str)      # (success, message)

    def __init__(self, action: str, version: str = "", parent=None):
        super().__init__(parent)
        self.action = action    # "fetch" | "update" | "switch"
        self.version = version

    def run(self):
        try:
            if self.action == "fetch":
                self._fetch()
            elif self.action == "update":
                self._update()
            elif self.action == "switch":
                self._switch()
        except Exception as e:
            self.done.emit(False, str(e))

    # ── 获取远端版本列表 ────────────────────────────────────────
    def _fetch(self):
        self.status.emit("正在连接 GitHub...")
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/tags",
                headers={"User-Agent": "GameLauncher/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                tags = json.loads(resp.read())
            versions = [t["name"] for t in tags]
        except Exception:
            # 网络不通时退回本地 git tags
            self.status.emit("网络不通，使用本地标签...")
            r = subprocess.run(
                ["git", "tag", "--sort=-version:refname"],
                capture_output=True, text=True, cwd=_ROOT,
            )
            versions = [v for v in r.stdout.strip().splitlines() if v]

        # 始终把 main 放在列表里
        if "main" not in versions:
            versions.append("main")
        self.versions_ready.emit(versions)
        self.done.emit(True, f"找到 {len(versions)} 个版本")

    # ── 拉取 main 最新代码 ──────────────────────────────────────
    def _update(self):
        self.status.emit("正在拉取最新代码...")
        subprocess.run(
            ["git", "fetch", "origin"],
            check=True, capture_output=True, cwd=_ROOT,
        )
        subprocess.run(
            ["git", "pull", "origin", "main"],
            check=True, capture_output=True, cwd=_ROOT,
        )
        self.done.emit(True, "更新成功，请重启应用生效")

    # ── 切换到指定版本 ──────────────────────────────────────────
    def _switch(self):
        self.status.emit(f"正在切换到 {self.version}...")
        subprocess.run(
            ["git", "fetch", "--tags"],
            check=True, capture_output=True, cwd=_ROOT,
        )
        subprocess.run(
            ["git", "checkout", self.version],
            check=True, capture_output=True, cwd=_ROOT,
        )
        self.done.emit(True, f"已切换到 {self.version}，请重启应用生效")
