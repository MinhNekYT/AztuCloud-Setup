@echo off
chcp 65001 >nul 2>&1
title AztuCloud Auto Setup

echo ========================================
echo    Chào mừng đến với script auto cho AztuCloud!
echo ========================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Vui lòng mở file lại với quyền Administrator
    pause
    exit /b
)

echo [*] Dang tai auto.ps1 tu GitHub...
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/MinhNekYT/AztuCloud-Setup/raw/refs/heads/main/auto.ps1' -OutFile 'C:\auto.ps1' -UseBasicParsing" >nul 2>&1
if %errorLevel% neq 0 (
    echo [-] Loi: Khong the tai auto.ps1 tu GitHub.
    pause
    exit /b
)

echo [*] Dang tai antiafk.py tu GitHub...
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/MinhNekYT/AztuCloud-Setup/raw/refs/heads/main/antiafk.py' -OutFile 'C:\antiafk.py' -UseBasicParsing" >nul 2>&1
if %errorLevel% neq 0 (
    echo [-] Loi: Khong the tai antiafk.py tu GitHub.
    pause
    exit /b
)

if not exist C:\auto.ps1 (
    echo [-] Loi: Khong tim thay C:\auto.ps1
    pause
    exit /b
)
if not exist C:\antiafk.py (
    echo [-] Loi: Khong tim thay C:\antiafk.py
    pause
    exit /b
)

echo [+] Tai thanh cong tat ca cac file.
echo [*] Dang chay auto.ps1...
powershell -ExecutionPolicy Bypass -File C:\auto.ps1
exit /b
