import json
import pika
import requests
from .Models.scripts_pje import *
from .utils.script_acessar_pje import preparar_ambiente
from .automation.pages.page_push_actions import AutomacaoPush
from .utils.script_salvar_log_return_csv import salvar_log_push_xlsx as save_log
from .utils.utils_limpeza import liberar_memoria_e_limpar_temporarios as clean_files_memory



# ================== CONFIG ==================
RABBIT_HOST = "192.168.11.38"
QUEUE_NAME = "q.push_add"
RETRY_DELAY = 5
first = True

RABBIT_USER = "ro.berto"
RABBIT_PASS = "Jrs-2018"

# 🔥 TRTs que NÃO devem ser processados
# TRT_EXCECOES = {'5'}   # set é mais rápido que list
TRT_EXCECOES = {}   # set é mais rápido que list

# ===========================================

TRT_COOLDOWN = {}  # { trt: datetime }
TRT_COOLDOWN_MINUTES = 10

# ===========================================

# Configure a URL correta do seu ambiente (ex: localhost ou produção)
API_BASE_URL = "http://192.168.11.24:8000"
# API_UPDATE_STATUS = f"{API_BASE_URL}/atividades/push/automation/update/status/"
API_UPDATE_STATUS = f"{API_BASE_URL}/atividades/push/automation/update/status/"
STATUS_ADD_SYSTEM = True


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


def normalizar_resultado_v0(retorno):
    """
    Normaliza o retorno da automação.
    Aceita: dict | str | None
    Retorna: (RESULTADO, mensagem_normalizada)
    """

    # 🔹 Caso None
    if retorno is None:
        return "ERRO", "Erro não detalhado"

    # 🔹 Caso dict (retorno padrão da automação)
    if isinstance(retorno, dict):
        sucesso = bool(retorno.get("sucesso"))
        texto = retorno.get("mensagem") or ""

    # 🔹 Caso string ou outro tipo
    else:
        texto = str(retorno)
        sucesso = "sucesso" in texto.lower()

    texto = texto.strip()
    texto_lower = texto.lower()

    # 🔥 REGRA DE NEGÓCIO
    if "já cadastrado" in texto_lower or "ja cadastrado" in texto_lower:
        return "AVISO", "Processo já cadastrado"

    if sucesso:
        return "SUCESSO", texto or "Operação realizada com sucesso"

    if "erro" in texto_lower or "falha" in texto_lower or "não encontrado" in texto_lower:
        return "ERRO", texto or "Erro retornado pela automação"

    # fallback conservador
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

    # Sem driver ainda
    clean_files_memory(driver=None)

    print("🧠 Criando driver Selenium...")
    driver = criar_driver()

    # automation = AutomacaoPush(driver)

    processo = None
    trt = None

    try:

        data = json.loads(body.decode())
        processo = data.get("numero_processo")
        trt = int(data.get("tribunal"))
        try:
            grau = "primeirograu" if int(data.get("grau")) == 1 else "segundograu"
        except Exception as e:
            print(f'- (except): {e}')
            grau = "primeirograu"

        print(f'- (Dicionário): {data}')
        print(f'- (Grau): {grau}')
        automation = AutomacaoPush(driver, trt)

        if abrir_pje(driver, trt, grau) is None:
            messege = 'Falha ao abrir PJe'
            print(f"- [STATUS]: {messege}")
            # Encaminhar para o Sistema
            status_operacao = atualizar_status_sistema(
                processo, 
                "ERRO",
                f"{messege}"
            )
            print(f'- (Status Update System): {status_operacao}')
            return {
                'data': data,
                'status': 'error', 
                'msg': f"{messege}"
            }
        
        if not garantir_autenticacao(driver, "paula"):
            messege = 'Falha ao se autenticar'
            print(f"- [STATUS]: {messege}")
            # Encaminhar para o Sistema
            status_operacao = atualizar_status_sistema(
                processo, 
                "ERRO",
                f"{messege}"
            )
            print(f'- (Status Update System): {status_operacao}')
            return {
                'data': data,
                'status': 'error', 
                'msg': f"{messege}"
            }
        
        
        if clicar_meu_painel(driver) is None:
            messege = 'Falha ao clicar no Menu do PJe'
            print(f"- [STATUS]: {messege}")
            # Encaminhar para o Sistema
            status_operacao = atualizar_status_sistema(
                processo, 
                "ERRO", 
                f"{messege}"
            )
            print(f'- (Status Update System): {status_operacao}')
            return {
                'data': data,
                'status': 'error', 
                'msg': f"{messege}"
            }
        
        garantir_perfil(driver, "Advogado")

        action = data.get("acao")
        print(f'- (AÇÃO): {action}')

        if action == 'create':
            mensagem = automation.function_main_cad_push(processo, None)

        elif action == 'delete':
            mensagem = automation.function_main_del_push(processo, None)

        else:
            messege = 'Action inválido.'
            print(f"- [STATUS]: {messege}")
            return {
                'data': data,
                'status': 'error', 
                'msg': f"{messege}"
            }
            

        resultado, mensagem_normalizada = normalizar_resultado(mensagem)
        print(f'- (STATUS): {resultado} | {mensagem_normalizada}')

        # 1. Salva log local (seu código atual)
        save_log(
            tribunal=f"TRT{trt}",
            numero_processo=processo,
            resultado=resultado,
            mensagem=mensagem_normalizada,
        )

        if STATUS_ADD_SYSTEM:
            # 2. CHAMADA NOVA: Atualiza o sistema
            status_operacao = atualizar_status_sistema(
                processo, 
                resultado, 
                mensagem_normalizada
            )
            print(f'- (Status da operação): {status_operacao}')

    except Exception as e:

        erro_txt = f"Exceção não tratada: {e}"
        print(f"❌ {erro_txt}")

        # 🔥 LOGA O ERRO CRÍTICO
        save_log(
            tribunal=trt,
            numero_processo=processo,
            resultado="ERRO",
            mensagem=erro_txt,
        )

        if STATUS_ADD_SYSTEM:
            # Tenta avisar o sistema sobre o erro crítico também
            atualizar_status_sistema(
                processo, 
                "ERRO", 
                erro_txt
            )

        time.sleep(RETRY_DELAY)


    clean_files_memory(driver)