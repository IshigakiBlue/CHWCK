@echo off
REM Run this from Task Scheduler. Adjust the paths below to match your setup.

cd /d "C:\path\to\chiswick_scraper"

REM Activate the virtual environment
call venv\Scripts\activate.bat

REM Timestamp for the log entry
echo ============================== >> run_log.txt
echo Run started: %date% %time% >> run_log.txt

python scraper.py >> run_log.txt 2>&1
python analyze.py >> run_log.txt 2>&1

echo Run finished: %date% %time% >> run_log.txt

deactivate
