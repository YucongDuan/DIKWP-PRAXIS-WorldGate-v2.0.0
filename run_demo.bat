@echo off
cd /d "%~dp0"
python dist\praxis_v2.pyz demo --out demo-%RANDOM%
pause
