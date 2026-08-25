@echo off
echo Starting Certify...
echo.

REM Activate the virtual environment
call venv\Scripts\activate

REM Set your Gmail credentials for sending real emails
REM Replace the values below with your actual Gmail address and App Password
set EMAIL_HOST_USER=ashaydeshpande2025@gmail.com
set EMAIL_HOST_PASSWORD=bzxzzlbwwoftekgt

REM Start the Django server
python manage.py runserver

pause
