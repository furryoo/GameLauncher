# GameLauncher

Windows 桌面自动化启动器，按顺序运行多个游戏自动化程序（BetterGI、OKWW 等），支持定时调度、运行历史记录和版本管理。

## 功能

- **任务列表**：添加/删除/拖拽排序，每个任务可设置可执行文件路径、超时、run_if 条件（总是/上一个成功/上一个失败）
- **多场景（Profile）**：创建多套配置，一键切换
- **定时调度**：每日指定时间自动运行，可按星期筛选
- **完成后动作**：无操作 / 关机 / 休眠
- **运行历史**：JSON 持久化，图表展示过去 14 天统计
- **Bark 推送**：任务完成后发送手机通知
- **版本管理**：源码模式用 git 切换版本，exe 模式从 GitHub Releases 下载更新
- **系统托盘**：最小化到托盘，后台运行

## 快速开始

**源码模式（开发）**

```bat
install_and_run.bat
```

依赖安装 + 启动一步完成。需要 Python 3.11+。

**打包 exe**

```bat
build.bat
```

输出到 `dist/GameLauncher.exe`。

**发布新版本**

```bat
git tag v1.x.x
release.bat
```

自动 build + 上传 exe + 创建 GitHub Release。需要提前安装 `gh` CLI 并登录。

## 配置文件

| 文件 | 说明 |
|------|------|
| `config.yaml` | 任务列表、调度、Bark URL 等，自动保存 |
| `history.json` | 运行历史记录，自动生成 |

两个文件均不进入 git，丢失不影响程序运行（会重新生成空文件）。

## 目录结构

```
GameLauncher/
├── main.py                  # 入口，UAC 提权检查
├── core/
│   ├── config.py            # YAML 配置读写
│   ├── enums.py             # CardStatus / RunResult 枚举
│   ├── history.py           # 运行历史持久化
│   ├── notifier.py          # Bark 推送
│   ├── process_manager.py   # 进程启动与监控
│   ├── scheduler.py         # 定时调度
│   ├── updater.py           # 版本管理（git / GitHub Releases）
│   └── utils.py             # 工具函数
└── ui/
    ├── main_window.py       # 主窗口
    ├── task_card.py         # 任务卡片
    ├── task_list.py         # 任务列表
    ├── theme.py             # 颜色常量
    └── version_view.py      # 版本管理界面
```

## 依赖

- PySide6 + pyside6-fluent-widgets
- APScheduler
- psutil
- PyYAML
