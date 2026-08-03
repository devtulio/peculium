@echo off
rem Abre o Peculium a partir do codigo-fonte.
rem Serve quando o executavel e barrado pelo Smart App Control do Windows:
rem o interpretador ja tem reputacao, o binario novo nao.
setlocal
cd /d "%~dp0"
python peculium.py %*
if errorlevel 1 (
  echo.
  echo Falhou. Se faltar dependencia, rode antes:
  echo     pip install -r requirements.txt
  pause
)
