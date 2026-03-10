@echo off
chcp 65001 >nul
echo ====================================
echo  Game Automation Launcher - 打包
echo ====================================
echo.

python -m pip install pyinstaller -q

pyinstaller --noconfirm --onefile --windowed ^
    --name "GameLauncher" ^
    --add-data "config.yaml;." ^
    main.py

echo.
echo 打包完成！exe 文件在 dist\GameLauncher.exe
pause
