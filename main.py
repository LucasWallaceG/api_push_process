import os
import threading
from flask import Flask, jsonify, request
from app.core.rabbitmq import Rabbitmq
from app.automation import main

app = Flask(__name__)

produtos = [] # Seu mock de dados


def callback_start_automacao(ch, method, properties, body):
    print(f'- [Consumers_1][key_received_push]: {body} | {type(body)}')
    print('- (Status): Iniciando a automação ...')
    msg_return = main.start_automation(body)
    print(f'- (Msg Resposta): {msg_return}')


def callback_post_return_status_push(ch, method, properties, body):
    print(f'- [Consumers_2][return_event_status_push_key]: {body} | {type(body)}')
    print('- (Status): Encaminhando status de retorno para o sistema dos formulários...')

# --- LÓGICA DO CONSUMER (WORKER) ---
def start_consumer_queue_1():
    # Aqui simulamos a chamada do seu Consumer
    rabbitmq_consumer = Rabbitmq(callback_start_automacao)
    rabbitmq_consumer.consumer(os.getenv('QUEUE_RECEIVED_EVENT_PUSH'))
    rabbitmq_consumer.start()
    print(" [Worker] RabbitMQ Consumer 1 iniciado e aguardando mensagens...")


def start_consumer_queue_2():
    # Aqui simulamos a chamada do seu Consumer
    rabbitmq_consumer = Rabbitmq(callback_post_return_status_push)
    rabbitmq_consumer.consumer(os.getenv('QUEUE_RETURN_EVENT_STATUS_PUSH'))
    rabbitmq_consumer.start()
    print(" [Worker] RabbitMQ Consumer 2 iniciado e aguardando mensagens de returno...")


# --- ROTAS DA API ---
@app.route('/push/received', methods=['GET'])
def listar_push():
    return jsonify(produtos), 200

@app.route('/push/received', methods=['POST'])
def send_push_queue():
    novo_produto = request.get_json()
    
    # 1. Adiciona na lista local (opcional)
    produtos.append(novo_produto)

    # 2. ENCAMINHAR PARA O RABBITMQ
    # Aqui você deve chamar o seu Producer para colocar o dado na fila
    rabbit_producer = Rabbitmq()
    rabbit_producer.publisher(novo_produto, os.getenv('RECEIVED_EVENT_PUSH_KEY'))
    
    print(f" [API] Recebido e enviado para fila: {novo_produto['numero_processo']}")
    
    return jsonify({
        "mensagem": "Encaminhado para fila de processamento!", 
        "item": novo_produto
    }), 201


if __name__ == '__main__':
    # Passo 1: Criar uma Thread para o Consumer não travar a API
    t = threading.Thread(target=start_consumer_queue_1)
    t.daemon = True  # Morre quando o programa principal fechar
    t.start()

    # Passo 2: Criar uma Thread para o Consumer 2 não travar a API
    t2 = threading.Thread(target=start_consumer_queue_2)
    t2.daemon = True  # Morre quando o programa principal fechar
    t2.start()

    # Passo 2: Rodar a API Flask (Fluxo principal)
    print(" [API] Flask rodando na porta 5000...")
    app.run(debug=True, use_reloader=False) # use_reloader=False evita duplicar a thread
    