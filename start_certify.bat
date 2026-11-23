@echo off
echo Starting Certify...
echo.

REM First run: make the virtual environment and install everything
if not exist venv (
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate
)

REM Your own keys live in local_env.bat (it is NOT uploaded to GitHub).
REM See the README, step 5.
if exist local_env.bat call local_env.bat

python manage.py migrate
python manage.py runserver

pause
