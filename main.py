import sys
import os

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

# Windows 管理员权限检查（仅 Windows 生效）
if sys.platform == "win32":
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        # 以管理员身份重新启动
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from qfluentwidgets import setTheme, Theme

from ui.main_window import MainWindow


def _icon_path() -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "icon.ico")


def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)
    app.setQuitOnLastWindowClosed(False)  # 允许最小化到托盘

    icon_path = _icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    setTheme(Theme.DARK)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
