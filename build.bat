@echo off
chcp 65001 >nul
echo ====================================
echo  Game Automation Launcher - 打包
echo ====================================
echo.

python -m pip install pyinstaller -q

pyinstaller --noconfirm --onefile --windowed ^
    --name "GameLauncher" ^
    --uac-admin ^
    --add-data "config.yaml;." ^
    --add-data "history.json;." ^
    --hidden-import "apscheduler.schedulers.background" ^
    --hidden-import "apscheduler.triggers.cron" ^
    --hidden-import "apscheduler.executors.pool" ^
    main.py

echo.
if exist dist\GameLauncher.exe (
    echo [成功] 打包完成：dist\GameLauncher.exe
) else (
    echo [失败] 打包出错，请检查上方日志
)
pause
