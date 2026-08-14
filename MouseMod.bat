@echo off
rem Development launcher (runs from source). The shipped app is dist\MouseMod.exe.
start "" "%~dp0.venv\Scripts\pythonw.exe" -m mousemod gui
