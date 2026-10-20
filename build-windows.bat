@echo off
rem Build a standalone eyeokuri folder and zip under build\. Double-click to run.
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

rem Fetch the face model now so the finished bundle works offline.
build\venv\Scripts\python -c "from pathlib import Path; from eyeokuri.sources.face_mesh import ensure_model; ensure_model(Path(r'%~dp0build\model\face_landmarker.task'))" || goto :fail

build\venv\Scripts\pyinstaller --noconfirm --clean --log-level WARN --name eyeokuri ^
    --add-data "%~dp0build\model\face_landmarker.task;model" ^
    --exclude-module pynput --distpath build\dist --workpath build\work --specpath build ^
    src\eyeokuri\__main__.py || goto :fail

copy /y THIRD_PARTY_NOTICES.md build\dist\eyeokuri\ >nul || goto :fail

powershell -NoProfile -Command "Compress-Archive -Force build\dist\eyeokuri build\eyeokuri-windows.zip" || goto :fail

echo.
echo Done. Copy build\eyeokuri-windows.zip to another PC, unzip it and run eyeokuri.exe.
pause
exit /b 0

:fail
echo.
echo Build failed. See the messages above.
pause
exit /b 1
