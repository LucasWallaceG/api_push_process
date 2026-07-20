import os
import json
import socket
import requests
from datetime import date
from app.core.screenshots import capturar_screenshot
from .Models.scripts_pje import *
from .utils.pje_push_api import inativar_push_por_codigo, consultar_codigo_push
from .utils.script_acessar_pje import preparar_ambiente
from .automation.pages.page_push_actions import AutomacaoPush, ProcessosScraper
from .utils.script_salvar_log_return_csv import salvar_log_push_xlsx as save_log
from .utils.utils_limpeza import liberar_memoria_e_limpar_temporarios as clean_files_memory


# ================== CONFIG ==================

# TRTs que NÃO devem ser processados
TRT_EXCECOES = {}

TRT_COOLDOWN = {}  # { trt: datetime }
TRT_COOLDOWN_MINUTES = 10

# Webhook Django (fallback quando a mensagem não traz callbacks).
# Configuravel via .env. O default usa a porta 6000 — a 8000 passou a ser a da
# propria API Flask deste servico, entao apontar para la criaria auto-referencia.
API_BASE_URL = os.getenv("API_BASE_URL", "http://192.168.11.24:6000").rstrip("/")
DJANGO_WEBHOOK_URL = f"{API_BASE_URL}/atividades/push/automation/update/status/"

# Porta em que a API Flask (que serve os screenshots) escuta.
PUSH_PUBLIC_PORT = os.getenv("PUSH_PUBLIC_PORT", os.getenv("PORT", "8000"))

# Timeout (segundos) do POST de retorno aos sistemas externos.
# Tupla (connect, read): conecta rapido, mas da folga para a resposta do destino
# (evita 'Read timed out' quando a app de origem demora a responder). Configuravel.
RETORNO_CONNECT_TIMEOUT = float(os.getenv("RETORNO_CONNECT_TIMEOUT", "5"))
RETORNO_READ_TIMEOUT = float(os.getenv("RETORNO_READ_TIMEOUT", "30"))
_RETORNO_TIMEOUT = (RETORNO_CONNECT_TIMEOUT, RETORNO_READ_TIMEOUT)


def _detectar_ip_local():
    """
    Descobre o IP da interface de rede usada para saida (LAN), sem depender de
    conexao real com a internet. O connect() UDP nao envia pacotes; apenas faz o
    SO escolher a interface. Fallback para 127.0.0.1 se nao for possivel.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _public_base_url():
    """
    URL base publica DESTE servico de push, usada para montar a URL ABSOLUTA do
    screenshot enviada aos sistemas externos.

    - Se a env PUSH_PUBLIC_URL estiver definida, usa-a (override explicito).
    - Caso contrario, detecta o IP local da maquina automaticamente, permitindo
      rodar em qualquer IP sem configuracao manual (porta via PUSH_PUBLIC_PORT).
    """
    override = os.getenv("PUSH_PUBLIC_URL")
    if override:
        return override.rstrip("/")
    return f"http://{_detectar_ip_local()}:{PUSH_PUBLIC_PORT}"


def _url_absoluta_screenshot(screenshot):
    """
    Converte o caminho relativo do screenshot ('/screenshots/xxx.png') em uma
    URL absoluta que o sistema externo consegue abrir. Retorna None se vazio.
    """
    if not screenshot:
        return None
    if screenshot.startswith("http://") or screenshot.startswith("https://"):
        return screenshot
    return f"{_public_base_url()}{screenshot}"


def enviar_retornos(data, resultado, mensagem, screenshot_url=None, codigo=None):
    """
    Posta o resultado em cada destino da lista callbacks da mensagem.
    - callbacks presente → POST {id, status, message, token, screenshot, codigo} em cada item.
    - callbacks ausente/vazio → fallback Django legado (processo/status/message/screenshot/codigo).

    screenshot_url: caminho relativo ('/screenshots/...') ou URL ja absoluta.
    codigo: ID da assinatura de push (CREATE) que o tarefas-jrs guarda e usa no DELETE.
    Os campos 'screenshot' e 'codigo' so entram no payload quando existem.
    """
    if not isinstance(data, dict):
        data = {}

    callbacks = data.get("callbacks") or []
    screenshot_abs = _url_absoluta_screenshot(screenshot_url)

    if callbacks:
        for cb in callbacks:
            url = cb.get("url")
            try:
                payload = {
                    "id": cb.get("id"),
                    "status": resultado,
                    "message": mensagem,
                    "token": cb.get("token"),
                }
                if screenshot_abs:
                    payload["screenshot"] = screenshot_abs
                if codigo is not None:
                    payload["codigo"] = codigo

                print(f"↪️  enviando retorno → {url} | payload: {payload}")
                resp = requests.post(url, json=payload, timeout=_RETORNO_TIMEOUT)

                if 200 <= resp.status_code < 300:
                    print(f"↩️  retorno OK → {url} [HTTP {resp.status_code}] ({resultado})")
                else:
                    # Chegou no destino, mas ele REJEITOU (nao foi 2xx).
                    print(
                        f"⚠️ retorno REJEITADO → {url} [HTTP {resp.status_code}] "
                        f"| corpo: {resp.text[:500]}"
                    )
            except Exception as e:
                # Nem chegou (DNS/conexao/timeout). Ex.: 'Read timed out', 'Connection refused'.
                print(f"❌ retorno NAO ENTREGUE → {url}: {type(e).__name__}: {e}")
    else:
        # Contrato Django legado (retrocompatível)
        status_map = {"SUCESSO": "SUCCESS", "AVISO": "SUCCESS", "ERRO": "ERROR"}
        payload = {
            "processo": data.get("numero_processo"),
            "status":   status_map.get(resultado, "ERROR"),
            "message":  mensagem,
        }
        if screenshot_abs:
            payload["screenshot"] = screenshot_abs
        if codigo is not None:
            payload["codigo"] = codigo
        try:
            response = requests.post(DJANGO_WEBHOOK_URL, json=payload, timeout=_RETORNO_TIMEOUT)
            if response.status_code == 200:
                print(f"✅ Webhook Django enviado: {data.get('numero_processo')} -> {resultado}")
            else:
                print(f"⚠️ Falha no webhook Django: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Erro ao chamar webhook Django: {e}")


def extrair_trt_do_processo(numero_processo):
    partes = numero_processo.split(".")
    return str(int(partes[3]))


def carregar_json_paginacao(trt):
    hoje = date.today().isoformat()
    path = f"processos_push_{hoje}.json"

    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        dados = json.load(f)

    mapa = {}
    for item in dados:
        if item.get("tribunal") == f"TRT{trt}":
            mapa[item["numero_processo"]] = int(item["pagina"])

    return mapa


def localizar_e_deletar_processo(automation, trt, processo):

    json_paginas = carregar_json_paginacao(trt)
    pagina_sugerida = json_paginas.get(processo)

    scraper = ProcessosScraper(
        automation.driver,
        trt,
        chaves_unicas=set(),
        data_execucao=None
    )

    # 🔹 tenta via JSON
    if pagina_sugerida:
        print(f"[INFO] Página sugerida pelo JSON: {pagina_sugerida}")
        automation.ir_para_pagina_json(pagina_sugerida)

        achado = scraper.localizar_processo(processo)
        if achado:
            automation.deletar_linha(achado["row"])
            return True, "Deletado com base na página do JSON"

    # 🔹 fallback
    print("[INFO] Fallback: busca sequencial")
    scraper.page = 1
    achado = scraper.localizar_processo(processo)

    if achado:
        automation.deletar_linha(achado["row"])
        return True, "Deletado após busca sequencial"

    return False, "Processo não localizado"


def normalizar_resultado(retorno):

    if retorno is None:
        return "ERRO", "Erro não detalhado"

    if isinstance(retorno, dict):
        sucesso = bool(retorno.get("sucesso"))
        texto = retorno.get("mensagem") or ""
    else:
        texto = str(retorno)
        sucesso = "sucesso" in texto.lower()

    texto = texto.strip().lower()

    if "já cadastrado" in texto:
        return "AVISO", "Processo já cadastrado"

    if "erro" in texto or "falha" in texto or "não encontrado" in texto:
        return "ERRO", texto

    if sucesso:
        return "SUCESSO", texto

    return "ERRO", texto or "Erro não detalhado"


def trt_em_cooldown(trt):
    ate = TRT_COOLDOWN.get(trt)
    if not ate:
        return False
    return datetime.now() < ate


def start_automation(body):

    """
        Example json received
        {
            'grau': '1',
            'tribunal': '6',
            'pagina': '',
            'numero_processo': '0000511-77.2025.5.06.0018',
            'acao': 'create',
            'status': '',
            'msg': ''
        }
    """

    # 1. Parsear payload primeiro (antes de qualquer operação pesada)
    data = json.loads(body.decode()) if isinstance(body, (bytes, bytearray)) else json.loads(body)
    processo = data.get("numero_processo")
    trt = data.get("tribunal")
    action = data.get("acao")

    try:
        trt = int(trt)
    except (TypeError, ValueError):
        trt = None

    try:
        grau = "primeirograu" if int(data.get("grau")) == 1 else "segundograu"
    except (TypeError, ValueError):
        grau = "primeirograu"

    print(f'- (Payload): {data}')
    print(f'- (Processo): {processo} | (TRT): {trt} | (Grau): {grau} | (Acao): {action}')

    driver = None

    try:
        # 2. Limpeza de memória e temporários
        clean_files_memory(driver=None)

        # 3. Criar driver Selenium
        print("Criando driver Selenium...")
        driver = criar_driver()

        automation = AutomacaoPush(driver, trt)

        # Helper: captura print da tela vinculado ao processo/acao/status.
        def _shot(status):
            return capturar_screenshot(driver, processo, action, status)

        if abrir_pje(driver, trt, grau) is None:
            msg = 'Falha ao abrir o navegador do PJe'
            print(f"- [STATUS]: {msg}")
            shot = _shot('ERRO')
            enviar_retornos(data, "ERRO", msg, shot)
            return {'data': data, 'status': 'ERRO', 'msg': msg, 'screenshot': shot}

        if not garantir_autenticacao(driver, "paula"):
            msg = 'Falha ao se autenticar no PJe'
            print(f"- [STATUS]: {msg}")
            shot = _shot('ERRO')
            enviar_retornos(data, "ERRO", msg, shot)
            return {'data': data, 'status': 'ERRO', 'msg': msg, 'screenshot': shot}

        if clicar_meu_painel(driver) is None:
            msg = 'Falha ao acessar o painel do PJe'
            print(f"- [STATUS]: {msg}")
            shot = _shot('ERRO')
            enviar_retornos(data, "ERRO", msg, shot)
            return {'data': data, 'status': 'ERRO', 'msg': msg, 'screenshot': shot}

        mensagem = None
        resolvido_por_api = False

        # 🚀 DELETE rápido via API: quando o tarefas-jrs manda o 'codigo' (ID
        # interno do registro), inativa direto pela API — sem trocar perfil,
        # abrir a tela de Push nem paginar. Qualquer falha cai no fluxo de UI.
        codigo = data.get("codigo")
        if action == 'delete' and codigo:
            print(f"- (DELETE API): tentando inativar codigo={codigo} ...")
            res_api = inativar_push_por_codigo(driver, codigo)
            if res_api.get("sucesso"):
                mensagem = res_api
                resolvido_por_api = True
                print(f"- (DELETE API): OK → {res_api.get('mensagem')}")
            else:
                print(f"- (DELETE API): falhou → {res_api.get('mensagem')} | "
                      f"seguindo para o fluxo de UI")

        if not resolvido_por_api:
            if not garantir_perfil(driver, "Advogado"):
                msg = ("Nao foi possivel trocar para o perfil 'Advogado'. "
                       "O perito pode nao ter esse perfil neste TRT.")
                print(f"- [STATUS]: {msg}")
                shot = _shot('ERRO')
                enviar_retornos(data, "ERRO", msg, shot)
                return {'data': data, 'status': 'ERRO', 'msg': msg, 'screenshot': shot}

            print(f'- (ACAO): {action}')

            pagina = data.get("pagina") or ""

            if action == 'create':
                mensagem = automation.function_main_cad_push(processo, None)
            elif action == 'delete':
                mensagem = automation.function_main_del_push(pagina, processo)
            else:
                msg = f'Acao invalida: {action}'
                print(f"- [STATUS]: {msg}")
                shot = _shot('ERRO')
                enviar_retornos(data, "ERRO", msg, shot)
                return {'data': data, 'status': 'ERRO', 'msg': msg, 'screenshot': shot}

        resultado, mensagem_normalizada = normalizar_resultado(mensagem)
        print(f'- (STATUS): {resultado} | {mensagem_normalizada}')

        if resultado == 'ERRO' and action == 'delete':
            print('- (Status): Tentar busca completa')
            sucesso, mensagem = localizar_e_deletar_processo(
                automation,
                trt,
                processo
            )
            print(f'- (STATUS): {sucesso}')
            print(f'- (MSG): {mensagem}')

            if sucesso:
                resultado = "SUCESSO"

            if "erro" in str(mensagem).lower() or "falha" in str(mensagem).lower() or "não encontrado" in str(mensagem).lower():
                resultado = "ERRO"

            mensagem_normalizada = mensagem


        # Código da assinatura de push (o tarefas-jrs guarda por grau e usa no
        # DELETE). Só faz sentido no CREATE que resultou em processo cadastrado
        # (SUCESSO) ou já cadastrado (AVISO). O POST de cadastro nao devolve o
        # codigo, entao consultamos via API na mesma sessao/grau.
        codigo_push = None
        if action == 'create' and resultado in ('SUCESSO', 'AVISO'):
            try:
                codigo_push = consultar_codigo_push(driver, processo)
                print(f"- (CODIGO PUSH): {codigo_push}")
            except Exception as e:
                print(f"⚠️ Falha ao consultar codigo push: {e}")

        # Print da tela vinculado ao processo. No cadastro, prefere o print
        # capturado no momento da confirmacao (dentro de function_main_cad_push,
        # enquanto o feedback ainda estava visivel); senao, captura agora.
        screenshot = getattr(automation, "ultimo_screenshot", None) or _shot(resultado)

        save_log(
            tribunal=f"TRT{trt}",
            numero_processo=processo,
            resultado=resultado,
            mensagem=mensagem_normalizada,
        )

        enviar_retornos(data, resultado, mensagem_normalizada, screenshot, codigo_push)

        return {
            'data': data,
            'status': f'{resultado}',
            'msg': f"{mensagem_normalizada}",
            'screenshot': screenshot,
            'codigo': codigo_push,
        }

    except Exception as e:

        print(f"[ERRO] Erro na automacao: {e}")

        # Mensagem mais clara para o usuario: inclui o detalhe real do erro.
        detalhe = str(e).strip().splitlines()[0] if str(e).strip() else "sem detalhe"
        msg_erro = f"Erro interno na automacao: {detalhe}"

        # Tenta capturar o estado da tela no momento da falha.
        try:
            screenshot = capturar_screenshot(driver, processo, action, "ERRO")
        except Exception:
            screenshot = ""

        save_log(
            tribunal=trt,
            numero_processo=processo,
            resultado="ERRO",
            mensagem=msg_erro,
        )

        enviar_retornos(data, "ERRO", msg_erro, screenshot)

        return {'data': data, 'status': 'ERRO', 'msg': msg_erro, 'screenshot': screenshot}

    finally:
        try:
            clean_files_memory(driver=driver)
        except Exception as cleanup_err:
            print(f"⚠️ Erro ao liberar recursos: {cleanup_err}")
