@echo off
chcp 65001 >nul

for /f "delims=" %%i in ('git describe --tags --exact-match HEAD 2^>nul') do set VERSION=%%i
if "%VERSION%"=="" (
    echo [错误] 当前 HEAD 没有 tag，请先: git tag vX.Y.Z
    pause & exit /b 1
)

echo %VERSION%> version.txt
pyinstaller --noconfirm --onefile --windowed ^
    --name "GameLauncher" --uac-admin ^
    --add-data "config.yaml;." --add-data "history.json;." --add-data "version.txt;." ^
    --hidden-import "apscheduler.schedulers.background" ^
    --hidden-import "apscheduler.triggers.cron" ^
    --hidden-import "apscheduler.executors.pool" ^
    main.py

if not exist dist\GameLauncher.exe ( echo [失败] 打包出错 & pause & exit /b 1 )

gh release create %VERSION% dist\GameLauncher.exe --title "%VERSION%" --generate-notes

echo [成功] %VERSION% 已发布
pause
