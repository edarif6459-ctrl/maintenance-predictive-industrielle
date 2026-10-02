@echo off
cd /d "%~dp0"
echo Installation des modules (1ere fois seulement)...
python -m pip install -r requirements.txt
echo.
echo Lancement de l'application... (Ctrl+C pour arreter)
python -m streamlit run app.py
pause
