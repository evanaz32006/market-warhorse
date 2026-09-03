@echo off
REM ============================================================================
REM  market-warhorse — daily scheduled run wrapper
REM  Point Task Scheduler at THIS file (Program/script = C:\Warhorse\run_daily.bat,
REM  Start in = C:\Warhorse). It runs app.py with the venv Python and captures ALL
REM  console output to a dated log so a failed/killed run is diagnosable after the fact.
REM
REM  IMPORTANT: a cold run fetches 500+ tickers (price + fundamentals + earnings),
REM  throttled — expect 10-20 MINUTES. It is NOT hung. Do not close the window; check
REM  the log file to watch progress instead.
REM ============================================================================

cd /d C:\Warhorse

REM Dated log file, e.g. output\run_2026-07-04.log (locale-independent date via PowerShell,
REM since wmic is removed on recent Windows 11 builds).
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set STAMP=%%d
set LOG=C:\Warhorse\output\run_%STAMP%.log

echo ============================================================ >> "%LOG%"
echo [run_daily] START %date% %time% >> "%LOG%"
echo ============================================================ >> "%LOG%"

REM -u = unbuffered stdout/stderr, so the log updates LIVE (Python otherwise block-buffers
REM when writing to a file and the log looks frozen for minutes).
C:\Warhorse\.venv\Scripts\python.exe -u app.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%

echo. >> "%LOG%"
if %RC%==0 (
    echo [run_daily] OK   %date% %time%  ^(exit 0^) >> "%LOG%"
) else (
    echo [run_daily] FAILED %date% %time%  ^(exit %RC%^) >> "%LOG%"
)

REM Propagate the real exit code so Task Scheduler's "Last Run Result" reflects it.
exit /b %RC%
