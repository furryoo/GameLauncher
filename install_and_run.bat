@echo off
chcp 65001 >nul
echo ====================================
echo  Game Automation Launcher - 安装依赖
echo ====================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 升级 pip
echo [1/3] 升级 pip...
python -m pip install --upgrade pip -q

:: 安装依赖
echo [2/3] 安装依赖包（首次运行可能需要几分钟）...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)

:: 启动程序
echo [3/3] 启动程序...
echo.
python main.py

pause
