import os
import json
import threading
from datetime import datetime
from flask import Flask, jsonify, request, render_template
from app.core.rabbitmq import Rabbitmq
from app.core.database import init_db, salvar_registro, buscar_registros
from app.automation import main

app = Flask(__name__)

# --- INICIALIZAR BANCO DE DADOS ---
init_db()

# --- TRACKING DE PROCESSOS ---
registros = []
_lock = threading.Lock()
_ordem_counter = 0


def registrar(processo, trt, grau, acao, status, msg=""):
    global _ordem_counter
    with _lock:
        _ordem_counter += 1

        # Atualiza registro existente (mesmo processo + acao) ou cria novo
        for r in registros:
            if r["processo"] == processo and r["acao"] == acao:
                r["status"] = status
                r["msg"] = msg
                r["data_hora"] = datetime.now().isoformat()
                salvar_registro(r)
                return r

        registro = {
            "ordem": _ordem_counter,
            "processo": processo,
            "trt": trt,
            "grau": grau,
            "acao": acao,
            "status": status,
            "msg": msg,
            "data_hora": datetime.now().isoformat(),
        }
        registros.insert(0, registro)

        # Persistir no SQLite
        salvar_registro(registro)

        return registro


# --- CALLBACK DO CONSUMER ---
def callback_start_automacao(ch, method, _properties, body):
    print(f'- [Consumer][received_push]: {body}')
    print('- (Status): Iniciando a automacao ...')

    # Parsear payload para tracking
    try:
        data = json.loads(body.decode()) if isinstance(body, (bytes, bytearray)) else json.loads(body)
    except Exception:
        data = {}

    processo = data.get("numero_processo")
    trt = data.get("tribunal")
    grau = data.get("grau")
    acao = data.get("acao")

    # Registrar como PROCESSANDO
    registrar(processo, trt, grau, acao, "PROCESSANDO", "Automacao em andamento...")

    try:
        msg_return = main.start_automation(body)
        print(f'- (Msg Resposta): {msg_return}')

        # Atualizar com resultado final
        if isinstance(msg_return, dict):
            status_final = msg_return.get("status", "ERRO").upper()
            msg_final = msg_return.get("msg", "")
        else:
            status_final = "ERRO"
            msg_final = str(msg_return)

        registrar(processo, trt, grau, acao, status_final, msg_final)

    except Exception as e:
        print(f'- (Erro critico no callback): {e}')
        registrar(processo, trt, grau, acao, "ERRO", "Erro interno na automacao")
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)
        print('- (ACK): Mensagem confirmada na fila.')


# --- LOGICA DO CONSUMER (WORKER) ---
def start_consumer():
    rabbit = Rabbitmq(callback_start_automacao)
    rabbit.consumer(os.getenv('QUEUE_RECEIVED_EVENT_PUSH'))
    rabbit.start()
    print(" [Worker] RabbitMQ Consumer iniciado e aguardando mensagens...")


# --- ROTAS ---
@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/api/dashboard')
def api_dashboard():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')

    registros_db = buscar_registros(data_inicio, data_fim)
    return jsonify({"registros": registros_db})


@app.route('/push/received', methods=['GET'])
def listar_push():
    with _lock:
        return jsonify(registros), 200


@app.route('/push/received', methods=['POST'])
def send_push_queue():
    print('- (API) - Enviando para fila de processamento...')

    novo_push = request.get_json(silent=True)

    if not isinstance(novo_push, dict):
        return jsonify({
            "mensagem": "Payload deve ser um objeto JSON (dict)"
        }), 400

    numero_processo = novo_push.get("numero_processo")
    if not numero_processo:
        return jsonify({
            "mensagem": "Campo obrigatorio ausente: numero_processo",
            "item": novo_push
        }), 400

    routing_key = os.getenv('RECEIVED_EVENT_PUSH_KEY')
    exchange = os.getenv('EXCHANGE')

    if not routing_key:
        return jsonify({
            "mensagem": "Variavel de ambiente RECEIVED_EVENT_PUSH_KEY nao configurada"
        }), 500

    if exchange is None:
        return jsonify({
            "mensagem": "Variavel de ambiente EXCHANGE nao configurada"
        }), 500

    try:
        rabbit_producer = Rabbitmq()
        rabbit_producer.publisher(novo_push, routing_key)

        # Registrar como AGUARDANDO
        registrar(
            numero_processo,
            novo_push.get("tribunal"),
            novo_push.get("grau"),
            novo_push.get("acao"),
            "AGUARDANDO",
            "Na fila de processamento",
        )

    except Exception as e:
        print(f"- (Erro): Falha ao publicar no RabbitMQ: {e}")
        return jsonify({
            "mensagem": "Falha ao encaminhar para a fila de processamento"
        }), 502

    print(f" [API] Recebido e enviado para fila: {numero_processo}")

    return jsonify({
        "mensagem": "Encaminhado para fila de processamento!",
        "item": novo_push
    }), 201


if __name__ == '__main__':
    print(" [API] Flask rodando na porta 5000...")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)