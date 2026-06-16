@echo off

echo ============================================
echo LP02 Logger installatie
echo ============================================
echo.

REM Controleer of Python bestaat
python --version >nul 2>&1

if errorlevel 1 (
    echo Python is niet gevonden.
    echo Installeer eerst Python 3.10 of hoger:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Python gevonden:
python --version

echo.
echo Pip upgraden...
python -m pip install --upgrade pip

echo.
echo Benodigde packages installeren...
python -m pip install ^
    yoctopuce ^
    pandas ^
    matplotlib

echo.
echo ============================================
echo Installatie voltooid
echo ============================================
echo.

pause
