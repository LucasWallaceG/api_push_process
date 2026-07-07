@echo off
REM ============================================================
REM  api_push_process - inicializacao dos servicos
REM
REM  start_all.py abre 1 janela de console para cada servico:
REM    [1] Dashboard Flask       -> main.py (http://localhost:5000)
REM    [2] Consumer Cadastro     -> consumer_cadastrar_push.py
REM    [3] Consumer Exclusao     -> consumer_excluir_push.py
REM
REM  Uso: salve este .bat na RAIZ do projeto e agende no
REM  Agendador de Tarefas com disparo "Ao efetuar logon".
REM  %~dp0 = pasta deste .bat (funciona mesmo com espacos/OneDrive).
REM ============================================================

REM Vai para a pasta do proprio .bat (raiz do projeto)
cd /d "%~dp0"

REM Python do ambiente virtual do projeto
set "PYEXE=%~dp0env\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [ERRO] Python do venv nao encontrado em:
    echo        %PYEXE%
    echo Verifique se a pasta 'env' existe na raiz do projeto.
    pause
    exit /b 1
)

echo Iniciando os servicos do api_push_process...
"%PYEXE%" start_all.py

REM start_all.py apenas dispara as 3 janelas e encerra;
REM esta janela pode fechar sozinha.
exit /b 0
