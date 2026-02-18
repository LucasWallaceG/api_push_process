import json
import pika
import requests
from .Models.scripts_pje import *
from .utils.script_acessar_pje import preparar_ambiente
from .automation.pages.page_push_actions import AutomacaoPush
from .utils.script_salvar_log_return_csv import salvar_log_push_xlsx as save_log


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

    print("🧠 Criando driver Selenium...")
    driver = criar_driver()

    automation = AutomacaoPush(driver)

    processo = None
    trt = None

    try:
        data = json.loads(body.decode())
        processo = data.get("numero_processo")
        print(f'- (Dicionário): {data}')

        return

        print(f"\n📥 Processo recebido da fila: {processo}")

        trt = extrair_trt_do_processo(processo)


        context = preparar_ambiente(
            driver=driver,
            automation=automation,
            trt=trt,
            perito="paula"
        )

        mensagem = automation.function_main_cad_push(processo, context)
        resultado, mensagem_normalizada = normalizar_resultado(mensagem)
        print(f'- (Result): {resultado} | {mensagem_normalizada}')

        # 1. Salva log local (seu código atual)
        save_log(
            tribunal=f"TRT{trt}",
            numero_processo=processo,
            resultado=resultado,
            mensagem=mensagem_normalizada,
        )

        if STATUS_ADD_SYSTEM:
            # 2. CHAMADA NOVA: Atualiza o sistema
            status_operacao = atualizar_status_sistema(processo, resultado, mensagem_normalizada)
            print(f'- (Status da operação): {status_operacao}')

        if resultado in ("SUCESSO" or "AVISO") and status_operacao:
            # ✅ remove da fila (inclusive se já estava cadastrado)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # ❌ erro real → volta para fila
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

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
            atualizar_status_sistema(processo, "ERRO", erro_txt)

        # ❌ erro real → volta para fila
        ch.basic_nack(
            delivery_tag=method.delivery_tag,
            requeue=True
        )

        time.sleep(RETRY_DELAY)
