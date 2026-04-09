@echo off
cd /d "C:\Users\ASUS\OneDrive\Desktop\NeuroPulseAI"
echo Launching NeuroPulseAI Fast Plotter...
"C:\Users\ASUS\anaconda3\Anaconda 2025\python.exe" fast_plotter.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo App crashed with exit code %ERRORLEVEL%.
    pause
)
