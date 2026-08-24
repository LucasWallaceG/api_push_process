import os
import sys
import json
import uuid
import threading
import time
import pika
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Perfil Firefox proprio deste servico (evita conflito com o consumer de cadastro,
# que roda em paralelo, e persiste o "lembrar minha escolha" do certificado).
os.environ["FIREFOX_PROFILE"] = "exclusao"

sys.path.insert(0, os.path.dirname(__file__))
from app.automation import main as automacao
from app.core.database import init_db, salvar_registro

# ================== CONFIG ==================
RABBIT_HOST = os.getenv("HOST_RABBITMQ", "192.168.11.38")
RABBIT_PORT = int(os.getenv("PORT_RABBITMQ", 5672))
RABBIT_VHOST = os.getenv("VHOST", "/myvhost")
RABBIT_USER = os.getenv("USER", "ro.berto")
RABBIT_PASS = os.getenv("PASSWORD", "Jrs-2018")

QUEUE_NAME = "queue_push_delete"
RETRY_DELAY = 5
# ============================================

_lock = threading.Lock()
_ordem_counter = 0


def _registrar(processo, trt, grau, acao, status, msg="", screenshot=None, req_id=None):
    global _ordem_counter
    with _lock:
        _ordem_counter += 1
        registro = {
            "ordem": _ordem_counter,
            "processo": processo,
            "trt": trt,
            "grau": grau,
            "acao": acao,
            "status": status,
            "msg": msg,
            "screenshot": screenshot,
            "req_id": req_id,
            "data_hora": datetime.now().isoformat(),
        }
    salvar_registro(registro)


def _processar(body):
    """Executa a automacao da mensagem.

    Roda numa thread separada para nao bloquear o loop de I/O do pika: uma
    automacao longa dentro do callback impede o envio de heartbeats e faz o
    broker derrubar a conexao.
    """
    processo = None
    data = {}
    # id unico desta requisicao: colapsa o ciclo de vida (PROCESSANDO -> final)
    # numa linha so, e mantem cada requisicao como uma linha propria no dashboard.
    req_id = str(uuid.uuid4())

    try:
        data = json.loads(body.decode()) if isinstance(body, (bytes, bytearray)) else json.loads(body)
        req_id = data.get("req_id") or req_id
        processo = data.get("numero_processo")
        trt = data.get("tribunal")
        grau = data.get("grau")
        acao = data.get("acao", "delete")

        print(f"\n[EXCLUSAO] Processo recebido da fila: {processo}")

        _registrar(processo, trt, grau, acao, "PROCESSANDO", "Automacao em andamento...", req_id=req_id)

        resultado = automacao.start_automation(body)

        status = resultado.get("status", "ERRO").upper() if isinstance(resultado, dict) else "ERRO"
        msg = resultado.get("msg", "") if isinstance(resultado, dict) else str(resultado)
        screenshot = resultado.get("screenshot") if isinstance(resultado, dict) else None

        _registrar(processo, trt, grau, acao, status, msg, screenshot, req_id=req_id)

        print(f"- [STATUS]: {status} | {msg}")
        print(f"[ACK] Processo {processo} finalizado com status {status} - removido da fila.")

    except Exception as e:
        print(f"[ERRO CRITICO] {e}")
        if processo:
            automacao.enviar_retornos(data, "ERRO", str(e))
            _registrar(processo, None, None, "delete", "ERRO", str(e), req_id=req_id)


def callback(ch, method, _properties, body):
    connection = ch.connection
    delivery_tag = method.delivery_tag

    def _worker():
        try:
            _processar(body)
        finally:
            # o ack precisa voltar para a thread do pika; chamar basic_ack
            # direto de outra thread corrompe a conexao.
            connection.add_callback_threadsafe(
                lambda: _ack_seguro(ch, delivery_tag)
            )

    threading.Thread(target=_worker, daemon=True).start()


def _ack_seguro(ch, delivery_tag):
    try:
        if ch.is_open:
            ch.basic_ack(delivery_tag=delivery_tag)
        else:
            # canal caiu durante a automacao: a mensagem volta para a fila
            # e sera reentregue apos a reconexao.
            print("[AVISO] Canal fechado antes do ACK; mensagem sera reentregue.")
    except Exception as e:
        print(f"[AVISO] Falha ao confirmar mensagem: {e}")


def start_consumer():
    credentials = pika.PlainCredentials(username=RABBIT_USER, password=RABBIT_PASS)

    params = pika.ConnectionParameters(
        host=RABBIT_HOST,
        port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )

    while True:
        connection = None
        try:
            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=callback
            )

            print(f"[EXCLUSAO] Aguardando mensagens na fila '{QUEUE_NAME}'...")
            channel.start_consuming()

        except KeyboardInterrupt:
            print(f"[EXCLUSAO] Encerrado pelo usuario.")
            break

        except pika.exceptions.ConnectionClosedByBroker as e:
            # broker reiniciado/parado (CONNECTION_FORCED ... 'shutdown')
            print(f"[RABBITMQ] Conexao fechada pelo broker: {e}")

        except pika.exceptions.AMQPChannelError as e:
            print(f"[RABBITMQ] Erro de canal: {e}")

        except pika.exceptions.AMQPConnectionError as e:
            # inclui broker indisponivel, queda de rede e heartbeat perdido
            print(f"[RABBITMQ] Conexao perdida: {e}")

        finally:
            try:
                if connection is not None and connection.is_open:
                    connection.close()
            except Exception:
                pass

        print(f"[RABBITMQ] Reconectando em {RETRY_DELAY}s...")
        time.sleep(RETRY_DELAY)


if __name__ == "__main__":
    init_db()
    start_consumer()
