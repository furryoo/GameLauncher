import json
import os
import subprocess
import sys
import urllib.request
from PySide6.QtCore import QThread, Signal

REPO = "furryoo/GameLauncher"
_ROOT = os.path.dirname(os.path.dirname(__file__))


def _read_token() -> str:
    """优先环境变量，其次用户目录下 ~/.gamelauncher_token"""
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok.strip()
    token_file = os.path.join(os.path.expanduser("~"), ".gamelauncher_token")
    if os.path.isfile(token_file):
        try:
            return open(token_file, encoding="utf-8").read().strip()
        except Exception:
            return ""
    return ""


def _api_headers() -> dict:
    headers = {
        "User-Agent": "GameLauncher/1.0",
        "Accept": "application/vnd.github+json",
    }
    tok = _read_token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return headers


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def current_version() -> str:
    if is_frozen():
        try:
            return open(os.path.join(sys._MEIPASS, "version.txt"), encoding="utf-8").read().strip()
        except Exception:
            return "unknown"
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
                self._frozen_fetch() if is_frozen() else self._fetch()
            elif self.action == "update":
                self._frozen_update() if is_frozen() else self._update()
            elif self.action == "switch":
                self._frozen_switch() if is_frozen() else self._switch()
        except Exception as e:
            self.done.emit(False, str(e))

    # ── 获取远端版本列表 ────────────────────────────────────────
    def _fetch(self):
        self.status.emit("正在连接 GitHub...")
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{REPO}/tags",
                headers=_api_headers(),
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

    # ── Frozen 路径：从 GitHub Releases 获取版本列表 ─────────────
    def _frozen_fetch(self):
        self.status.emit("正在连接 GitHub Releases...")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases",
            headers=_api_headers(),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read())
        versions = [r["tag_name"] for r in releases if r.get("assets")]
        self.versions_ready.emit(versions)
        self.done.emit(True, f"找到 {len(versions)} 个版本")

    def _frozen_update(self):
        self._frozen_download_and_prepare(target_version=None)

    def _frozen_switch(self):
        self._frozen_download_and_prepare(target_version=self.version)

    def _frozen_download_and_prepare(self, target_version):
        self.status.emit("正在连接 GitHub Releases...")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/releases",
            headers=_api_headers(),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read())

        if target_version is None:
            release = next((r for r in releases if r.get("assets")), None)
        else:
            release = next((r for r in releases if r["tag_name"] == target_version and r.get("assets")), None)

        if release is None:
            self.done.emit(False, "未找到对应 Release 或无附件")
            return

        asset = next((a for a in release["assets"] if a["name"] == "GameLauncher.exe"), None)
        if asset is None:
            self.done.emit(False, "Release 中未找到 GameLauncher.exe")
            return

        url = asset["browser_download_url"]
        dest = os.path.join(os.environ.get("TEMP", ""), "GameLauncher_new.exe")
        self._download_asset(url, dest)
        self._write_updater_bat(dest)
        self.done.emit(True, "下载完成，点击重启以完成更新")

    def _download_asset(self, url: str, dest: str):
        req = urllib.request.Request(url, headers=_api_headers())
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 512 * 1024
            with open(dest, "wb") as f:
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    downloaded += len(data)
                    if total:
                        pct = int(downloaded / total * 100)
                        self.status.emit(f"下载中 {pct}%")

    def _write_updater_bat(self, new_exe: str) -> str:
        bat_path = os.path.join(os.environ.get("TEMP", ""), "gl_updater.bat")
        current_exe = sys.executable
        bat_content = (
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"
            ":retry\r\n"
            f'move /y "{new_exe}" "{current_exe}" 2>nul || goto retry\r\n'
            f'start "" "{current_exe}"\r\n'
            'del "%~f0"\r\n'
        )
        with open(bat_path, "w", encoding="gbk") as f:
            f.write(bat_content)
        return bat_path
