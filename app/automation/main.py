import json
import requests
from .Models.scripts_pje import *
from .utils.script_acessar_pje import preparar_ambiente
from .automation.pages.page_push_actions import AutomacaoPush
from .utils.script_salvar_log_return_csv import salvar_log_push_xlsx as save_log
from .utils.utils_limpeza import liberar_memoria_e_limpar_temporarios as clean_files_memory


# ================== CONFIG ==================

# TRTs que NÃO devem ser processados
TRT_EXCECOES = {}

TRT_COOLDOWN = {}  # { trt: datetime }
TRT_COOLDOWN_MINUTES = 10

# Webhook Django
API_BASE_URL = "http://192.168.11.24:8000"
API_UPDATE_STATUS = f"{API_BASE_URL}/atividades/push/automation/update/status/"


def atualizar_status_sistema(numero_processo, resultado, mensagem):
    """
    Envia o status da automação para o sistema Django atualizar a tabela.
    """
    status_map = {
        "SUCESSO": "SUCCESS",
        "AVISO": "SUCCESS",  # Consideramos aviso como sucesso de cadastro? Ou crie um status 'WARNING'
        "ERRO": "ERROR"
    }

    status_django = status_map.get(resultado, "ERROR")

    payload = {
        "processo": numero_processo,
        "status": status_django,
        "message": mensagem
    }

    try:
        response = requests.post(API_UPDATE_STATUS, json=payload, timeout=10)
        if response.status_code == 200:
            print(f"✅ Status atualizado no sistema: {numero_processo} -> {status_django}")
            return True
        else:
            print(f"⚠️ Falha ao atualizar sistema: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Erro ao chamar API do sistema: {e}")
        return False


def extrair_trt_do_processo(numero_processo):
    partes = numero_processo.split(".")
    return str(int(partes[3]))


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

    if sucesso:
        return "SUCESSO", texto

    if "erro" in texto or "falha" in texto or "não encontrado" in texto:
        return "ERRO", texto

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

        if abrir_pje(driver, trt, grau) is None:
            msg = 'Falha ao abrir o navegador do PJe'
            print(f"- [STATUS]: {msg}")
            atualizar_status_sistema(processo, "ERRO", msg)
            return {'data': data, 'status': 'error', 'msg': msg}

        if not garantir_autenticacao(driver, "paula"):
            msg = 'Falha ao se autenticar no PJe'
            print(f"- [STATUS]: {msg}")
            atualizar_status_sistema(processo, "ERRO", msg)
            return {'data': data, 'status': 'error', 'msg': msg}

        if clicar_meu_painel(driver) is None:
            msg = 'Falha ao acessar o painel do PJe'
            print(f"- [STATUS]: {msg}")
            atualizar_status_sistema(processo, "ERRO", msg)
            return {'data': data, 'status': 'error', 'msg': msg}

        garantir_perfil(driver, "Advogado")

        print(f'- (ACAO): {action}')

        if action == 'create':
            mensagem = automation.function_main_cad_push(processo, None)
        elif action == 'delete':
            mensagem = automation.function_main_del_push(processo, None)
        else:
            msg = f'Acao invalida: {action}'
            print(f"- [STATUS]: {msg}")
            atualizar_status_sistema(processo, "ERRO", msg)
            return {'data': data, 'status': 'error', 'msg': msg}

        resultado, mensagem_normalizada = normalizar_resultado(mensagem)
        print(f'- (STATUS): {resultado} | {mensagem_normalizada}')

        save_log(
            tribunal=f"TRT{trt}",
            numero_processo=processo,
            resultado=resultado,
            mensagem=mensagem_normalizada,
        )

        atualizar_status_sistema(processo, resultado, mensagem_normalizada)

        return {
            'data': data,
            'status': f'{resultado}',
            'msg': f"{mensagem_normalizada}"
        }

    except Exception as e:

        erro_txt = f"Erro na automacao: {e}"
        print(f"[ERRO] {erro_txt}")

        save_log(
            tribunal=trt,
            numero_processo=processo,
            resultado="ERRO",
            mensagem=erro_txt,
        )

        atualizar_status_sistema(processo, "ERRO", erro_txt)

        return {'data': data, 'status': 'error', 'msg': erro_txt}

    finally:
        clean_files_memory(driver=driver)
