@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto path_error
if not exist ".venv\Scripts\python.exe" goto env_error
echo Starting Duhe Tongtian. Open http://127.0.0.1:7865
echo Keep this window open while playing.
".venv\Scripts\python.exe" -X utf8 -m duhe.app_v2_draft
echo The server has stopped.
pause
exit /b
:env_error
echo Project environment not found. See the README file.
pause
exit /b 1
:path_error
echo Could not open the project folder.
pause
exit /b 1
