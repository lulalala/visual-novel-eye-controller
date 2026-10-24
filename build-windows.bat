@echo off
rem Build the eyeokuri app folder, a zip of it and, with Inno Setup 6 installed, an installer under build\. Double-click to run.
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
for /f %%v in ('build\venv\Scripts\python -c "import eyeokuri; print(eyeokuri.__version__)"') do set "VERSION=%%v"

rem Fetch the face model now so the finished bundle works offline.
build\venv\Scripts\python -c "from pathlib import Path; from eyeokuri.sources.face_mesh import ensure_model; ensure_model(Path(r'%~dp0build\model\face_landmarker.task'))" || goto :fail
build\venv\Scripts\python tools\make_ico.py build\eyeokuri.ico || goto :fail

rem The GUI, without a console window.
build\venv\Scripts\pyinstaller --noconfirm --clean --log-level WARN --name eyeokuri --windowed ^
    --icon "%~dp0build\eyeokuri.ico" ^
    --add-data "%~dp0build\model\face_landmarker.task;model" ^
    --add-data "%~dp0src\eyeokuri\icons;eyeokuri\icons" ^
    --exclude-module pynput --distpath build\dist --workpath build\work --specpath build ^
    src\eyeokuri\gui\launch.py || goto :fail

copy /y LICENSE build\dist\eyeokuri\ >nul || goto :fail
copy /y THIRD_PARTY_NOTICES.md build\dist\eyeokuri\ >nul || goto :fail

powershell -NoProfile -Command "Compress-Archive -Force build\dist\eyeokuri build\eyeokuri-windows.zip" || goto :fail

set "ISCC="
for %%p in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
    if exist %%p set "ISCC=%%~p"
)
if defined ISCC (
    "%ISCC%" /Q /DAppVersion=%VERSION% eyeokuri.iss || goto :fail
    echo.
    echo Done. build\eyeokuri-setup.exe installs eyeokuri %VERSION%; build\eyeokuri-windows.zip is the same app without an installer.
) else (
    echo.
    echo Done. build\eyeokuri-windows.zip holds eyeokuri %VERSION%. To also build the installer, install Inno Setup 6 ^(winget install JRSoftware.InnoSetup^) and run this again.
)
if not defined CI pause
exit /b 0

:fail
echo.
echo Build failed. See the messages above.
if not defined CI pause
exit /b 1
