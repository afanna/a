@echo off
REM ============================================================================
REM CI Script for Card Aesthetic Scoring System (Windows)
REM 
REM Usage: ci.bat [--score image.png] [--query "text"]
REM ============================================================================

setlocal enabledelayedexpansion

set PYTHON=python
set PROJECT_DIR=%~dp0
REM RapidOCR?????????

echo ========================================
echo Card Aesthetic Scoring System - CI Check
echo ========================================
echo.

REM ---------------------------------------------------------------------------
REM 1. Install dependencies
REM ---------------------------------------------------------------------------
echo [1/3] Installing dependencies...
%PYTHON% -m pip install -r "%PROJECT_DIR%requirements.txt" --quiet
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to install dependencies
    exit /b 1
)
echo       Done.
echo.

REM ---------------------------------------------------------------------------
REM 2. Run tests
REM ---------------------------------------------------------------------------
echo [2/3] Running test suite...
set PYTHONPATH=%PROJECT_DIR%
%PYTHON% -m pytest "%PROJECT_DIR%tests/" -v --tb=short
if %ERRORLEVEL% neq 0 (
    echo ERROR: Tests failed
    exit /b 1
)
echo       All tests passed.
echo.

REM ---------------------------------------------------------------------------
REM 3. Score sample card (if provided)
REM ---------------------------------------------------------------------------
if "%1"=="--score" (
    echo [3/3] Scoring card: %2
    set QUERY=%4
    if "%QUERY%"=="" set QUERY=sample query
    %PYTHON% -m card_scorer.cli.main --image "%2" --query "!QUERY!" --output "%PROJECT_DIR%reports\"
    if %ERRORLEVEL% neq 0 (
        echo WARNING: Card scored FAIL
    ) else (
        echo       Card scored PASS
    )
) else (
    echo [3/3] No sample card provided, skipping scoring.
)

echo.
echo ========================================
echo CI Check Complete
echo ========================================
exit /b 0
