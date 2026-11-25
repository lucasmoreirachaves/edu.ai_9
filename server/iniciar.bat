@echo off
setlocal
cd /d "%~dp0"

if not defined LOCALAPPDATA goto :erro_localappdata

set "APP_DATA=%LOCALAPPDATA%\EduAI"
set "VENV_DIR=%APP_DATA%\venv"
set "EDU_DB=%APP_DATA%\edu.db"

if not exist "%APP_DATA%" (
  mkdir "%APP_DATA%"
  if errorlevel 1 goto :erro_dados
)

if not exist "%EDU_DB%" if exist "%~dp0edu.db" (
  copy /Y "%~dp0edu.db" "%EDU_DB%" >nul || goto :erro_dados
)
if not exist "%APP_DATA%\uploads" if exist "%~dp0uploads\" (
  robocopy "%~dp0uploads" "%APP_DATA%\uploads" /E /NFL /NDL /NJH /NJS /NP >nul
  if errorlevel 8 goto :erro_dados
)

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
  )
)
if not defined PYTHON_CMD goto :erro_python

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Criando ambiente Python na pasta do usuario...
  %PYTHON_CMD% -m venv "%VENV_DIR%" || goto :erro_ambiente
)

"%VENV_DIR%\Scripts\python.exe" -c "import fastapi, uvicorn, bcrypt, jwt, multipart, pypdf" >nul 2>&1
if errorlevel 1 (
  echo Instalando dependencias...
  "%VENV_DIR%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" || goto :erro_dependencias
)

echo.
echo  Site:        http://localhost:8000
echo  Plataforma:  http://localhost:8000/app/
echo  Contas teste: professor@ / aluno@ / gestor@escolateste.edu.br  ^|  Instituicao: escola-teste
echo  Admin geral:  admin@plataforma.edu.br  ^|  Instituicao: plataforma
echo                Senha de todas: Teste@2026
echo  Dados:       %APP_DATA%
echo.
"%VENV_DIR%\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof

:erro_localappdata
echo Nao foi possivel localizar a pasta de dados do usuario do Windows.
goto :erro_final

:erro_dados
echo Falha ao criar ou copiar os dados em "%LOCALAPPDATA%\EduAI".
goto :erro_final

:erro_python
echo Python 3.11 ou superior nao foi encontrado.
echo Instale o Python para o seu usuario e marque "Add Python to PATH".
goto :erro_final

:erro_ambiente
echo Falha ao criar o ambiente Python em "%VENV_DIR%".
goto :erro_final

:erro_dependencias
echo Falha ao instalar dependencias. Verifique a conexao com a internet ou o acesso ao PyPI.
goto :erro_final

:erro_final
echo.
pause
exit /b 1
