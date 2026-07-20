import os
import json
import uuid
import threading
from datetime import datetime
from dotenv import load_dotenv

# Carrega o .env explicitamente. Antes isso vinha por efeito colateral do import
# de app.core.rabbitmq — se os imports fossem reordenados, PORT/API_BASE_URL
# voltariam silenciosamente aos defaults.
load_dotenv()

from flask import Flask, jsonify, request, render_template, send_from_directory, abort
from app.core.rabbitmq import Rabbitmq
from app.core.database import init_db, salvar_registro, buscar_registros
from app.core.screenshots import SCREENSHOT_DIR
from app.automation import main

app = Flask(__name__)

# --- INICIALIZAR BANCO DE DADOS ---
init_db()

# --- TRACKING DE PROCESSOS ---
registros = []
_lock = threading.Lock()
_ordem_counter = 0


def registrar(processo, trt, grau, acao, status, msg="", screenshot=None, req_id=None):
    global _ordem_counter
    with _lock:
        _ordem_counter += 1

        # Atualiza registro existente (por req_id, senao por processo+acao) ou cria novo
        for r in registros:
            mesmo = (r.get("req_id") == req_id) if req_id else (
                r["processo"] == processo and r["acao"] == acao
            )
            if mesmo:
                r["status"] = status
                r["msg"] = msg
                if screenshot:
                    r["screenshot"] = screenshot
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
            "screenshot": screenshot,
            "req_id": req_id,
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
    req_id = data.get("req_id") or str(uuid.uuid4())

    # Registrar como PROCESSANDO
    registrar(processo, trt, grau, acao, "PROCESSANDO", "Automacao em andamento...", req_id=req_id)

    try:
        msg_return = main.start_automation(body)
        print(f'- (Msg Resposta): {msg_return}')

        # Atualizar com resultado final
        if isinstance(msg_return, dict):
            status_final = msg_return.get("status", "ERRO").upper()
            msg_final = msg_return.get("msg", "")
            screenshot_final = msg_return.get("screenshot")
        else:
            status_final = "ERRO"
            msg_final = str(msg_return)
            screenshot_final = None

        registrar(processo, trt, grau, acao, status_final, msg_final, screenshot_final, req_id=req_id)

    except Exception as e:
        print(f'- (Erro critico no callback): {e}')
        registrar(processo, trt, grau, acao, "ERRO", "Erro interno na automacao", req_id=req_id)
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


@app.route('/docs')
def docs():
    """Guia da API (HTML), para pessoas e agentes de IA."""
    return render_template('api_docs.html', base_url=request.url_root)


@app.route('/api/spec')
def api_spec():
    """
    Contrato da API em JSON, pensado para agentes/chats de IA consumirem
    programaticamente. Complementa a pagina /docs (versao humana).
    """
    base = request.url_root
    return jsonify({
        "servico": "Push Monitor - automacao de cadastro/exclusao no Push do PJe",
        "base_url": base,
        "documentacao_humana": f"{base}docs",
        "assincrono": True,
        "resumo": (
            "POST /push/received enfileira a acao. A resposta 201 confirma apenas o "
            "ENFILEIRAMENTO; o resultado real chega depois via POST nos callbacks."
        ),
        "endpoints": [
            {
                "metodo": "POST",
                "caminho": "/push/received",
                "descricao": "Enfileira um cadastro (create) ou exclusao (delete) de push.",
                "content_type": "application/json",
                "campos": {
                    "numero_processo": {"tipo": "string", "obrigatorio": True,
                                        "exemplo": "0000511-77.2025.5.06.0018"},
                    "acao": {"tipo": "string", "obrigatorio": True, "valores": ["create", "delete"]},
                    "tribunal": {"tipo": "string", "obrigatorio": True, "exemplo": "6",
                                 "descricao": "numero do TRT, sem zeros a esquerda"},
                    "grau": {"tipo": "string", "obrigatorio": True, "valores": ["1", "2"]},
                    "codigo": {"tipo": "integer", "obrigatorio": False, "exemplo": 1701632,
                               "descricao": ("ID da assinatura de push, devolvido no retorno do create. "
                                             "Use no delete: torna a exclusao muito mais rapida. E POR GRAU.")},
                    "callbacks": {"tipo": "array", "obrigatorio": False,
                                  "item": {"url": "string", "id": "string", "token": "string"},
                                  "descricao": "Destinos do POST de retorno."},
                    "pagina": {"tipo": "string", "obrigatorio": False,
                               "descricao": "Dica de pagina para o delete quando nao houver codigo."},
                    "req_id": {"tipo": "string", "obrigatorio": False,
                               "descricao": "Gerado automaticamente se ausente; identifica a requisicao."},
                },
                "respostas": {
                    "201": "Enfileirado com sucesso",
                    "400": "Payload invalido ou numero_processo ausente",
                    "502": "Falha ao publicar na fila (RabbitMQ indisponivel)",
                },
            },
            {"metodo": "GET", "caminho": "/api/dashboard",
             "descricao": "Lista os registros persistidos.",
             "query": {"data_inicio": "AAAA-MM-DD (opcional)", "data_fim": "AAAA-MM-DD (opcional)"},
             "observacao": "Sem parametros retorna o dia atual. O campo screenshot vem RELATIVO."},
            {"metodo": "GET", "caminho": "/push/received",
             "descricao": "Registros da sessao atual em memoria."},
            {"metodo": "GET", "caminho": "/screenshots/<arquivo>",
             "descricao": "PNG do print de tela da execucao."},
            {"metodo": "GET", "caminho": "/docs", "descricao": "Guia da API em HTML."},
            {"metodo": "GET", "caminho": "/api/spec", "descricao": "Este contrato."},
        ],
        "callback": {
            "descricao": "POST que o servico envia para cada callbacks[].url ao concluir.",
            "corpo": {
                "id": "o mesmo id que voce enviou no callback",
                "status": "SUCESSO | AVISO | ERRO",
                "message": "mensagem real devolvida pelo PJe - exibir LITERALMENTE",
                "token": "o token que voce enviou - validar",
                "screenshot": "URL absoluta do print (pode nao vir)",
                "codigo": "somente no create: ID da assinatura - guardar para usar no delete",
            },
            "exemplo": {
                "id": "ca53bfff-b8e5-4ab2-9776-3bbdead6113f",
                "status": "SUCESSO",
                "message": "processo cadastrado com sucesso",
                "token": "SEU_TOKEN",
                "screenshot": f"{base}screenshots/0000511-77.2025.5.06.0018_create_SUCESSO_20260707_143512.png",
                "codigo": 1701632,
            },
        },
        "status_possiveis": {
            "AGUARDANDO": "na fila",
            "PROCESSANDO": "robo executando no PJe",
            "SUCESSO": "concluido",
            "AVISO": "concluido com ressalva (ex.: processo ja estava cadastrado)",
            "ERRO": "falhou - ver 'message' e 'screenshot'",
        },
        "regras_para_agentes": [
            "O 201 do POST confirma apenas o enfileiramento, nao a conclusao no PJe.",
            "Exiba a 'message' do callback literalmente; nao troque por texto generico.",
            "Guarde o 'codigo' recebido no create e reutilize no delete do MESMO grau.",
            "Anexe o 'screenshot' como comprovacao, tanto em sucesso quanto em erro.",
            "Responda o callback rapidamente (2xx); faca downloads de forma assincrona.",
        ],
    })


@app.route('/screenshots/<path:filename>')
def servir_screenshot(filename):
    # send_from_directory ja protege contra path traversal (../).
    try:
        return send_from_directory(SCREENSHOT_DIR, filename)
    except Exception:
        abort(404)


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

    # id unico da requisicao: vai na mensagem para o consumer reaproveitar,
    # ligando AGUARDANDO -> PROCESSANDO -> final numa unica linha do dashboard.
    req_id = novo_push.get("req_id") or str(uuid.uuid4())
    novo_push["req_id"] = req_id

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
            req_id=req_id,
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
    porta = int(os.getenv("PORT", "8000"))
    print(f" [API] Flask rodando na porta {porta}...")
    app.run(host="0.0.0.0", port=porta, debug=True, use_reloader=False)