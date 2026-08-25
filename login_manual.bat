@echo off
REM ============================================================================
REM  Re-semeadura manual da sessao do PJe.
REM
REM  Abre o Firefox NO MESMO diretorio de perfil que a automacao usa. O operador
REM  faz o login uma vez (resolvendo o captcha, se houver) e fecha o navegador:
REM  a sessao fica salva no perfil e os consumers voltam a entrar sem relogar.
REM
REM  ATENCAO: este projeto tem UM PERFIL POR SERVICO (a env FIREFOX_PROFILE de
REM  cada consumer). Re-semear "cadastro" NAO re-semeia "exclusao" — rode uma
REM  vez para cada perfil que estiver com a sessao expirada.
REM
REM  Uso:  login_manual.bat [perfil] [trt] [grau]
REM        login_manual.bat cadastro 6
REM        login_manual.bat exclusao 6 segundograu
REM ============================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PERFIL_NOME=%~1"
if "%PERFIL_NOME%"=="" set "PERFIL_NOME=cadastro"

set "TRT=%~2"
if "%TRT%"=="" set "TRT=6"

set "GRAU=%~3"
if "%GRAU%"=="" set "GRAU=primeirograu"

set "PERFIL=%~dp0firefox_profiles\%PERFIL_NOME%"
set "URL=https://pje.trt%TRT%.jus.br/%GRAU%/login.seam"

set "FF=%ProgramFiles%\Mozilla Firefox\firefox.exe"
if not exist "%FF%" set "FF=%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"
if not exist "%FF%" (
    echo [ERRO] Firefox nao encontrado. Ajuste a variavel FF neste arquivo.
    pause
    exit /b 1
)

if not exist "%PERFIL%" mkdir "%PERFIL%"

echo.
echo   Perfil : %PERFIL%
echo   URL    : %URL%
echo.
echo   PASSO 1: confirme que o consumer deste perfil (%PERFIL_NOME%) esta PARADO.
echo            O Firefox nao abre o mesmo perfil em dois lugares ao mesmo tempo.
echo   PASSO 2: faca o login normal e RESOLVA o captcha ate cair no painel.
echo   PASSO 3: feche o Firefox - a sessao fica salva no perfil.
echo   PASSO 4: reinicie o consumer.
echo.
pause

REM -no-remote evita anexar a uma instancia ja aberta com outro perfil.
"%FF%" -profile "%PERFIL%" -no-remote "%URL%"

endlocal
