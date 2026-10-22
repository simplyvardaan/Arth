@echo off
title Arth - Paytm AI Voice & Vision Copilot
cd /d "%~dp0"
echo ==============================================================
echo ARTH — Paytm AI Voice and Vision Payment Copilot
echo Moto: "Arth: it means wealth. It means meaning."
echo ==============================================================
echo.
echo Launching camera and audio pipelines...
.\venv\Scripts\python.exe -u arth.py
echo.
pause
