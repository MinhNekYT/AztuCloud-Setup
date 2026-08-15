@echo off
echo Đang tải và chạy script auto.ps1...
powershell -ExecutionPolicy Bypass -Command "& { Invoke-Expression (Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/zenixbot0101/Moonlight-Web-2.0/refs/heads/main/auto.ps1' -UseBasicParsing).Content }"
pause
