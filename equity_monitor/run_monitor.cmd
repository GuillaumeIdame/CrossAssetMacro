@echo off
REM Equity Monitor - refresh quotidien (Planificateur Windows, lun-ven 06:45 UTC).
REM Creer la tache (depuis ce dossier, en PowerShell admin) :
REM   schtasks /Create /TN "EquityMonitor" /TR "\"%~dp0run_monitor.cmd\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 06:45 /F
REM   (06:45 UTC : regler l'horloge de la tache en UTC, ou convertir en heure locale si le PC n'est pas en UTC.)
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set D=%%c%%b%%a
set STAMP=%D%_%time:~0,2%%time:~3,2%
set STAMP=%STAMP: =0%
set LOG=logs\run_monitor_%STAMP%.log

echo [%date% %time%] start update_monitor.py > "%LOG%"
py -3.13 update_monitor.py %* >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo [%date% %time%] update_monitor.py exit %RC% >> "%LOG%"
if not "%RC%"=="0" (
    echo [%date% %time%] update_monitor.py failed with code %RC% > LAST_ERROR.txt
    echo see %LOG% >> LAST_ERROR.txt
    type "%LOG%" | findstr /i "error traceback" >> LAST_ERROR.txt
    exit /b %RC%
)

echo [%date% %time%] start backtest_signals.py >> "%LOG%"
py -3.13 backtest_signals.py >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo [%date% %time%] backtest_signals.py exit %RC% >> "%LOG%"
if not "%RC%"=="0" (
    echo [%date% %time%] backtest_signals.py failed with code %RC% > LAST_ERROR.txt
    echo see %LOG% >> LAST_ERROR.txt
    exit /b %RC%
)

REM re-bundle data.js now that backtest.json exists
py -3.13 update_monitor.py --bundle-only >> "%LOG%" 2>&1
if exist LAST_ERROR.txt del LAST_ERROR.txt
echo [%date% %time%] done >> "%LOG%"
endlocal
exit /b 0
