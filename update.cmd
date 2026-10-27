@echo off
setlocal
cd /d "%~dp0"
python -X utf8 publish.py %*
set "cards_exit=%errorlevel%"
if not "%cards_exit%"=="0" echo Update failed. See the error above.
pause
exit /b %cards_exit%
