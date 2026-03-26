import os
import threading
from flask import Flask, jsonify, request
from app.core.rabbitmq import Rabbitmq
from app.automation import main

app = Flask(__name__)

processos = [] # Seu mock de dados


def callback_start_automacao(ch, method, properties, body):
    print(f'- [Consumer][received_push]: {body}')
    print('- (Status): Iniciando a automação ...')
    try:
        msg_return = main.start_automation(body)
        print(f'- (Msg Resposta): {msg_return}')
    except Exception as e:
        print(f'- (Erro crítico no callback): {e}')
    finally:
        ch.basic_ack(delivery_tag=method.delivery_tag)
        print('- (ACK): Mensagem confirmada na fila.')


# --- LÓGICA DO CONSUMER (WORKER) ---
def start_consumer():
    rabbit = Rabbitmq(callback_start_automacao)
    rabbit.consumer(os.getenv('QUEUE_RECEIVED_EVENT_PUSH'))
    rabbit.start()
    print(" [Worker] RabbitMQ Consumer iniciado e aguardando mensagens...")


# --- ROTAS DA API ---
@app.route('/push/received', methods=['GET'])
def listar_push():
    return jsonify(processos), 200

@app.route('/push/received', methods=['POST'])
def send_push_queue():
    print('- (API) - Enviando para fila de processamento...')
    # novo_push = request.get_json()
    
    # 1. Adiciona na lista local (opcional)
    # processos.append(novo_push)

    novo_push = request.get_json(silent=True)

    if not isinstance(novo_push, dict):
        return jsonify({
            "mensagem": "Payload deve ser um objeto JSON (dict)"
        }), 400

    numero_processo = novo_push.get("numero_processo")
    if not numero_processo:
        return jsonify({
            "mensagem": "Campo obrigatório ausente: numero_processo",
            "item": novo_push
        }), 400

    routing_key = os.getenv('RECEIVED_EVENT_PUSH_KEY')
    exchange = os.getenv('EXCHANGE')

    if not routing_key:
        return jsonify({
            "mensagem": "Variável de ambiente RECEIVED_EVENT_PUSH_KEY não configurada"
        }), 500

    if exchange is None:
        return jsonify({
            "mensagem": "Variável de ambiente EXCHANGE não configurada"
        }), 500

    try:
        processos.append(novo_push)

        # 2. ENCAMINHAR PARA O RABBITMQ
        # Aqui você deve chamar o seu Producer para colocar o dado na fila
        # rabbit_producer = Rabbitmq()
        # rabbit_producer.publisher(novo_push, os.getenv('RECEIVED_EVENT_PUSH_KEY'))

        rabbit_producer = Rabbitmq()
        rabbit_producer.publisher(novo_push, routing_key)

    except Exception as e:
        print(f"- (Erro): Falha ao publicar no RabbitMQ: {e}")
        return jsonify({
            "mensagem": "Falha ao encaminhar para a fila de processamento"
        }), 502

    print(f" [API] Recebido e enviado para fila: {novo_push['numero_processo']}")
    
    return jsonify({
        "mensagem": "Encaminhado para fila de processamento!", 
        "item": novo_push
    }), 201


if __name__ == '__main__':
    # Thread do consumer RabbitMQ (não trava a API)
    t = threading.Thread(target=start_consumer, daemon=True)
    t.start()

    # API Flask (fluxo principal)
    print(" [API] Flask rodando na porta 5000...")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    