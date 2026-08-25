@echo off
REM ============================================================================
REM  Roda um script deste projeto com o modo diagnostico do PJe LIGADO.
REM
REM  Grava url, titulo, marcadores, screenshot e HTML de cada etapa da
REM  autenticacao em .\diagnostico\ - responde EM QUE TELA a automacao parou.
REM
REM  Uso:  diagnostico_pje.bat [script]
REM        diagnostico_pje.bat consumer_cadastrar_push.py
REM        diagnostico_pje.bat consumer_excluir_push.py
REM ============================================================================
setlocal
cd /d "%~dp0"

set "PJE_DIAG=1"

set "SCRIPT=%~1"
if "%SCRIPT%"=="" set "SCRIPT=consumer_cadastrar_push.py"

if exist "%~dp0env\Scripts\python.exe" (
    set "PY=%~dp0env\Scripts\python.exe"
) else (
    set "PY=python"
)

echo [DIAG] PJE_DIAG=1 - capturas em "%~dp0diagnostico"
echo [DIAG] Executando: %SCRIPT%
"%PY%" "%SCRIPT%"

endlocal
