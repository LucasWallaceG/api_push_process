import os
import sys
import json
import time
import pika
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
from app.automation import main as automacao

# ================== CONFIG ==================
RABBIT_HOST = os.getenv("HOST_RABBITMQ", "192.168.11.38")
RABBIT_PORT = int(os.getenv("PORT_RABBITMQ", 5672))
RABBIT_VHOST = os.getenv("VHOST", "/myvhost")
RABBIT_USER = os.getenv("USER", "ro.berto")
RABBIT_PASS = os.getenv("PASSWORD", "Jrs-2018")

QUEUE_NAME = "queue_push_insert"
RETRY_DELAY = 5
# ============================================


def callback(ch, method, properties, body):
    processo = None

    try:
        data = json.loads(body.decode()) if isinstance(body, (bytes, bytearray)) else json.loads(body)
        processo = data.get("numero_processo")

        print(f"\n[CADASTRO] Processo recebido da fila: {processo}")

        resultado = automacao.start_automation(body)

        status = resultado.get("status", "ERRO").upper() if isinstance(resultado, dict) else "ERRO"
        msg = resultado.get("msg", "") if isinstance(resultado, dict) else str(resultado)

        print(f"- [STATUS]: {status} | {msg}")

        print(f"[ACK] Processo {processo} finalizado com status {status} — removido da fila.")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        print(f"[ERRO CRITICO] {e}")
        ch.basic_ack(delivery_tag=method.delivery_tag)


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

    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=callback
    )

    print(f"[CADASTRO] Aguardando mensagens na fila '{QUEUE_NAME}'...")
    channel.start_consuming()


if __name__ == "__main__":
    start_consumer()
