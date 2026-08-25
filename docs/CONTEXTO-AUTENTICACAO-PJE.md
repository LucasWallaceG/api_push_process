# Autenticação do PJe sem cair no captcha — contexto para replicar em outros projetos

Documento de referência para um agente de IA implementar, em **outro projeto**, a
mesma estratégia de autenticação no PJe (TRTs) que já roda em produção na
automação de intimações. Descreve o problema, a solução, o código essencial, as
armadilhas descobertas na prática e como validar.

Contexto de origem: automação Python + Selenium/Firefox (geckodriver) em Windows,
que acessa `https://pje.trt{N}.jus.br` para vários TRTs em sequência.

---

## 1. O problema

O login do PJe passa pelo SSO **PDPJ (Keycloak)**. Uma automação que roda o dia
inteiro tende a repetir o ciclo completo de login a cada TRT e a cada ciclo:

```
login.seam -> botão PDPJ -> certificado digital -> senha (diálogo nativo) -> OTP
```

O Keycloak trata essa repetição como força bruta e passa a exigir um **captcha
anti-robô** ("Vamos confirmar que você é humano", seleção de relógios/imagens).
A partir daí a automação trava: não há tela de certificado para clicar, e cada
nova tentativa de login/OTP **piora** o bloqueio.

Resolver o captcha por robô é inviável e contraproducente. A solução é **não
precisar logar**.

---

## 2. A estratégia

Três peças que se sustentam mutuamente:

1. **Perfil persistente do Firefox.** O Selenium, por padrão, cria um perfil
   temporário e o apaga ao fechar — nenhum cookie sobrevive. Com um perfil fixo
   em disco, o cookie de sessão do PJe/PDPJ persiste entre execuções.

2. **Re-semeadura manual da sessão.** Um humano roda um `.bat` que abre o Firefox
   **no mesmo perfil**, faz o login uma vez resolvendo o captcha e fecha. A
   sessão fica salva no perfil.

3. **Autenticação dirigida por estado.** Antes de qualquer ação de login, a
   automação **lê o estado da tela**. Se já está autenticada, não faz nada. Só
   executa passos de login quando a tela realmente pede. Se detecta captcha,
   **para** e orienta a re-semeadura.

O efeito combinado: a automação praticamente nunca loga, então o Keycloak nunca
aciona o captcha. Quando a sessão expira (dias), um humano re-semeia uma vez.

> **Regra de ouro:** relogar "por via das dúvidas" é o que causa o problema.
> Todo passo de login deve ser condicionado ao estado observado na tela.

---

## 3. Peça 1 — driver com perfil persistente

```python
def criar_driver():
    options = FirefoxOptions()

    # Perfil FIXO. Sem isso o Selenium cria um perfil temporário a cada execução
    # e o apaga ao fechar — nenhuma sessão/escolha de certificado sobrevive.
    perfil_dir = os.path.abspath("firefox_profile")
    os.makedirs(perfil_dir, exist_ok=True)

    # Se um Firefox anterior morreu segurando o perfil, o parent.lock impede a
    # nova instância de abrir e o driver fica pendurado. Lock órfão é removível;
    # lock em uso não é -> encerra os processos.
    lock = os.path.join(perfil_dir, "parent.lock")
    if os.path.exists(lock):
        try:
            os.remove(lock)
        except OSError:
            os.system("taskkill /IM firefox.exe /F >nul 2>&1")
            time.sleep(3)
            try:
                os.remove(lock)
            except OSError:
                pass

    options.add_argument("-profile")
    options.add_argument(perfil_dir)

    # Não pedir permissão para abrir o app externo do certificado/assinador
    # (equivale a marcar "Lembrar minha escolha" + "Permitir").
    options.set_preference("security.external_protocol_requires_permission", False)
    options.set_preference("network.protocol-handler.external-default", True)
    options.set_preference("network.protocol-handler.warn-external-default", False)

    service = FirefoxService(
        executable_path=os.path.abspath("Drivers/geckodriver.exe"),
        log_output="geckodriver.log",
    )
    driver = webdriver.Firefox(service=service, options=options)

    # Sem timeout o Selenium espera até 300s por página e trava indefinidamente
    # se a comunicação com o navegador degringolar.
    driver.set_page_load_timeout(60)
    driver.maximize_window()
    return driver
```

**Obrigatório:** `firefox_profile/` no `.gitignore`. A sessão é local e sensível;
não viaja pelo repositório. Cada máquina re-semeia a sua.

---

## 4. Peça 2 — detecção do captcha

Comparação robusta: resolve entidades HTML, remove acentos e normaliza para
minúsculas antes de procurar os marcadores. Sem isso, `é` / `&ecirc;` / `e` não
casam entre si e a detecção falha de forma silenciosa.

```python
import html as html_lib
import unicodedata

# Sempre comparados em minúsculas e SEM acentos (ver _normalizar_pagina).
MARCADORES_CAPTCHA = (
    "confirmar que voce e humano",
    "vamos confirmar que voce",
    "escolha todos(as)",
    "conclua a verificacao de seguranca",
    "verifica se voce nao e um bot",
    'class="g-recaptcha"',
    'class="h-captcha"',
    "/recaptcha/api2/",
    "hcaptcha.com/captcha",
)


def _normalizar_pagina(texto):
    texto = html_lib.unescape(texto or "")
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def captcha_presente(driver):
    try:
        pagina = _normalizar_pagina(driver.page_source)
    except Exception:
        return False
    return any(m in pagina for m in MARCADORES_CAPTCHA)
```

Ajuste `MARCADORES_CAPTCHA` ao texto que o seu tribunal/tenant realmente exibe —
capture o HTML uma vez (ver modo diagnóstico) e confirme.

---

## 5. Peça 3 — máquina de estados

O captcha é checado **primeiro**: é bloqueio terminal, não adianta seguir o roteiro.

```python
def detectar_estado_pje(driver):
    if captcha_presente(driver):
        return "CAPTCHA"

    if driver.find_elements(By.XPATH, '//*[@aria-label="Meu Painel"]'):
        return "AUTENTICADO"

    if driver.find_elements(By.ID, "otp"):
        return "CODIGO_ACESSO"

    if driver.find_elements(
        By.XPATH, "//a[.//span[contains(text(), 'Seu certificado digital')]]"
    ):
        return "CERTIFICADO"

    if driver.find_elements(By.ID, "btnSsoPdpj"):
        return "PDPJ"

    return "DESCONHECIDO"
```

### Seletores de referência

| Estado / elemento | Seletor |
|---|---|
| Autenticado | `//*[@aria-label="Meu Painel"]` |
| Código de acesso (OTP) | `id="otp"` |
| Escolha de certificado | `//a[.//span[contains(text(), 'Seu certificado digital')]]` |
| Botão SSO do PDPJ | `id="btnSsoPdpj"` |
| Papel/perfil do usuário | `//span[contains(@class, 'papel-usuario')]` (usar o **último**) |
| Trocar perfil | `//button[@aria-label='Trocar Órgão Julgador ou Perfil']` |
| Selecionar perfil | `//button[contains(@aria-label, '<Perfil>')]` |

URL de entrada: `https://pje.trt{N}.jus.br/primeirograu/login.seam`

---

## 6. Peça 4 — o laço de autenticação

```python
def garantir_autenticacao(driver, usuario, max_tentativas=8):
    """Autentica conduzindo pelo ESTADO da tela.

    - AUTENTICADO   -> retorna True SEM relogar (reaproveita a sessão do perfil).
    - CAPTCHA       -> para e retorna False (orienta a re-semeadura manual).
    - CODIGO_ACESSO -> OTPs ESPAÇADOS e limitados (rajada de OTP também traz captcha).
    """
    OTP_MAX = 3
    ESPERA_OTP = 20
    otps = 0
    tentativa = 0

    while tentativa < max_tentativas:
        tentativa += 1
        estado = detectar_estado_pje(driver)
        print(f"[AUTH] Estado detectado: {estado}")

        if estado == "AUTENTICADO":
            return True

        if estado == "CAPTCHA":
            avisar_operador_para_re_semear()   # mensagem clara + canal de log
            return False

        if estado == "PDPJ":
            clicar_botao_pdpj(driver)

        elif estado == "CERTIFICADO":
            clicar_certificado_digital(driver)
            preencher_senha_desktop(usuario)   # diálogo nativo (pywinauto)

        elif estado == "CODIGO_ACESSO":
            if otps >= OTP_MAX:
                return False
            if otps:
                time.sleep(ESPERA_OTP)         # espaça reenvios
            otps += 1
            codigo = gerar_codigo(usuario)
            if not codigo:
                continue
            codigo_acesso(driver, codigo)
            clicar_validar_codigo(driver)

        else:
            time.sleep(1)

    return False
```

### Como integrar no laço principal

```python
for trt in trts:
    if primeira_vez:
        abrir_pje(driver, trt)
    else:
        alterar_trt(driver, trt)          # driver.get(login.seam do novo TRT)

    if garantir_autenticacao(driver, usuario) is not True:
        continue                          # pula este TRT; não insiste

    garantir_perfil(driver, perfil)       # troca de perfil, se necessário
    ...
```

Só isso. **Nenhuma chamada direta** a `clicar_botao_pdpj`, `clicar_certificado_digital`,
`preencher_senha_desktop` ou ao laço de OTP fora de `garantir_autenticacao` — é
essa disciplina que impede o relogin desnecessário.

---

## 7. Peça 5 — re-semeadura manual (`login_manual.bat`)

O ponto crítico é apontar para **o mesmo diretório de perfil** que o Selenium usa.

```bat
@echo off
cd /d "%~dp0"
chcp 65001 >nul

set "PERFIL=%~dp0firefox_profile"
set "TRT=%~1"
if "%TRT%"=="" set "TRT=6"
set "URL=https://pje.trt%TRT%.jus.br/primeirograu/login.seam"

set "FF=%ProgramFiles%\Mozilla Firefox\firefox.exe"
if not exist "%FF%" set "FF=%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"

echo   PASSO 1: confirme que a AUTOMACAO esta PARADA (o Firefox nao abre o
echo            mesmo perfil em dois lugares ao mesmo tempo).
echo   PASSO 2: faca o login normal e RESOLVA o captcha ate cair no painel.
echo   PASSO 3: feche o Firefox - a sessao fica salva no perfil.
echo   PASSO 4: reinicie a automacao.
pause

"%FF%" -profile "%PERFIL%" -no-remote "%URL%"
```

`-no-remote` evita anexar a uma instância já aberta com outro perfil.

---

## 8. Peça 6 — modo diagnóstico

Quando o login falha, o log normal só diz "erro ao clicar X" — não diz **em que
tela** parou. O modo diagnóstico responde isso.

Ligado por variável de ambiente, **desligado por padrão**: com a flag off,
nenhuma linha executa e o comportamento de produção é idêntico.

```python
DIAGNOSTICO = os.getenv("PJE_DIAG", "0").strip().lower() not in ("", "0", "false", "nao", "não")
DIAG_DIR = os.path.abspath("diagnostico")

# Mesmos seletores do detectar_estado_pje, checados um a um: assim o
# diagnóstico responde "qual marcador faltou" em vez de só dizer DESCONHECIDO.
DIAG_MARCADORES = {
    "AUTENTICADO (aria-label='Meu Painel')": (By.XPATH, '//*[@aria-label="Meu Painel"]'),
    "CODIGO_ACESSO (id='otp')": (By.ID, "otp"),
    "CERTIFICADO (link 'Seu certificado digital')": (
        By.XPATH, "//a[.//span[contains(text(), 'Seu certificado digital')]]"),
    "PDPJ (id='btnSsoPdpj')": (By.ID, "btnSsoPdpj"),
}


def diagnostico_capturar(driver, etapa, extra=""):
    """Grava URL, título, marcadores, screenshot e HTML em ./diagnostico/.

    NUNCA levanta exceção: diagnóstico não pode derrubar a automação.
    """
    if not DIAGNOSTICO:
        return
    try:
        os.makedirs(DIAG_DIR, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        nome = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(etapa))[:60]
        base = os.path.join(DIAG_DIR, f"{carimbo}_{nome}")
        # base + ".txt"  -> url, título, extra, marcadores um a um, captcha_presente
        # base + ".png"  -> driver.save_screenshot(...)
        # base + ".html" -> driver.page_source
    except Exception as e:
        print(f"[DIAG] captura falhou (ignorado): {e}")
```

**Onde instrumentar:** nas funções **compartilhadas**, não nos scripts de
orquestração. Um projeto costuma ter vários `main*.py` com fluxos ligeiramente
diferentes; instrumentar as funções cobre todos de uma vez.

Pontos que valem a pena: `abrir_pje`, `clicar_botao_pdpj` (antes **e** depois do
clique), `alterar_trt`, entrada de `garantir_autenticacao`, cada volta do laço
com o estado detectado, esgotamento das tentativas, entrada e falha da troca de
perfil, falha ao abrir o painel.

Acompanhe de um `.bat` que apenas define a flag e chama o script:

```bat
set "PJE_DIAG=1"
set "SCRIPT=%~1"
if "%SCRIPT%"=="" set "SCRIPT=main.py"
python "%SCRIPT%"
```

E `diagnostico/` no `.gitignore`.

---

## 9. Armadilhas descobertas na prática

**Cada TRT tem sessão própria.** Só o SSO (PDPJ/Keycloak) é compartilhado. Todo
TRT novo obriga o round-trip `login.seam` → PDPJ → Keycloak → volta. Não assuma
que estar autenticado no TRT 6 significa estar autenticado no TRT 10.

**Não há espera após o clique no PDPJ.** No ramo `PDPJ`, a implementação de
origem clica e reavalia o estado imediatamente; a página em trânsito vira
`DESCONHECIDO` e o laço só dorme 1s por volta. Se o redirect do SSO demorar mais
que a margem restante, a autenticação desiste sem motivo real. **Prefira esperar
a saída do estado `PDPJ`** (ex.: `WebDriverWait` até o botão ficar stale ou até
outro marcador aparecer) em vez de reavaliar na hora.

**Perfil aberto em dois lugares.** O Firefox recusa abrir o mesmo perfil
simultaneamente. A re-semeadura manual exige a automação parada, e o
`parent.lock` órfão precisa ser tratado (ver seção 3).

**Console Windows em cp1252 não encoda emoji.** Um `print` com emoji levanta
`UnicodeEncodeError`. Se isso acontece **dentro** do bloco de diagnóstico, o
diagnóstico derruba a automação — exatamente o oposto do objetivo. Mantenha os
prints do diagnóstico em **ASCII puro**, inclusive os de fallback no `except`.

**`AUTENTICADO` depende de um marcador do painel.** Se o tribunal levar a uma
tela intermediária (escolha de órgão julgador, aviso) antes do painel, nenhum
marcador casa e o estado fica `DESCONHECIDO`. Verifique com o modo diagnóstico
antes de concluir que o login falhou.

**Troca de perfil não é login.** Falha ao trocar de perfil costuma ser sintoma de
redirect ainda em andamento (o `.papel-usuario` ainda não existe), não de sessão
inválida. Diagnostique antes de mexer no login.

**A sessão não viaja pelo git.** `firefox_profile/` é ignorado. Ao publicar em
outras máquinas, cada uma precisa rodar a re-semeadura manual uma vez.

---

## 10. Checklist de implantação

- [ ] `firefox_profile/` e `diagnostico/` no `.gitignore`
- [ ] `criar_driver` com perfil fixo + tratamento de `parent.lock` + `set_page_load_timeout`
- [ ] `captcha_presente` com normalização de acentos/entidades
- [ ] `detectar_estado_pje` checando CAPTCHA primeiro
- [ ] `garantir_autenticacao` com retorno imediato em `AUTENTICADO` e limite/espaçamento de OTP
- [ ] Nenhuma chamada direta a passos de login fora de `garantir_autenticacao`
- [ ] `login_manual.bat` apontando para o mesmo diretório de perfil, com `-no-remote`
- [ ] Modo diagnóstico opt-in, prints ASCII, captura que nunca levanta exceção
- [ ] Instrumentação nas funções compartilhadas, não nos `main*`
- [ ] Mensagem de captcha orientando o operador a rodar a re-semeadura

---

## 11. Como validar

1. **Sessão viva:** com o perfil re-semeado, rodar sobre 2+ tribunais. O log deve
   mostrar `[AUTH] Estado detectado: AUTENTICADO` (ou `PDPJ` → `AUTENTICADO`) e
   **nenhum** envio de OTP.
2. **Sessão morta:** apagar o perfil e rodar. Deve percorrer
   `PDPJ` → `CERTIFICADO` → `CODIGO_ACESSO` → `AUTENTICADO`, com no máximo 3 OTPs
   espaçados de 20s.
3. **Captcha:** ao detectar, a automação deve **parar** com a mensagem de
   orientação, sem tentar novo login.
4. **Flag off:** sem `PJE_DIAG`, a pasta `diagnostico/` não é criada e o log não
   tem nenhuma linha `[DIAG]`.

---

## 12. Estado conhecido / pendências

A implementação de origem tem um ponto ainda **não resolvido**: falhas de login
ao **trocar de TRT**. A hipótese principal é a ausência de espera após o clique
no PDPJ (seção 9), mas isso ainda não foi confirmado por diagnóstico. Ao
replicar em outro projeto, considere já implementar a espera explícita pela saída
do estado `PDPJ` em vez de copiar o comportamento atual.
