@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set PY=py
) else (
  set PY=python
)

%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "dwrean Apothiki.spec" del /q "dwrean Apothiki.spec"

%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name "dwrean Apothiki" app.py

if not exist portable mkdir portable
copy /y "dist\dwrean Apothiki.exe" "portable\dwrean Apothiki.exe"
if not exist "portable\data" mkdir "portable\data"
if not exist "portable\data\images" mkdir "portable\data\images"

echo.
echo ==========================================
echo Build completed.
echo Portable file: portable\dwrean Apothiki.exe
echo ==========================================
pause
