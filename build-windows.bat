@echo off
rem Build a standalone vn-eye folder and zip under build\. Double-click to run.
setlocal
cd /d "%~dp0"

rem A separate venv, so packages installed in the dev .venv don't end up in the bundle.
if not exist build\venv\Scripts\python.exe (
    echo Creating build environment in build\venv ...
    py -3 -m venv build\venv || python -m venv build\venv || goto :fail
    build\venv\Scripts\python -m pip install -q pyinstaller || goto :fail
)

rem Reinstall so the bundle picks up the current source.
build\venv\Scripts\python -m pip install -q --force-reinstall --no-deps . || goto :fail
build\venv\Scripts\python -m pip install -q . || goto :fail

build\venv\Scripts\pyinstaller --noconfirm --clean --log-level WARN --name vn-eye ^
    --exclude-module pynput --distpath build\dist --workpath build\work --specpath build ^
    src\vn_eye\__main__.py || goto :fail

powershell -NoProfile -Command "Compress-Archive -Force build\dist\vn-eye build\vn-eye-windows.zip" || goto :fail

echo.
echo Done. Copy build\vn-eye-windows.zip to another PC, unzip it and run vn-eye.exe.
pause
exit /b 0

:fail
echo.
echo Build failed. See the messages above.
pause
exit /b 1
