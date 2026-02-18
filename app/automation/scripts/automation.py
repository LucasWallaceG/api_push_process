import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

automation = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
db_dir = os.path.join(basedir, 'db-sqlite')
os.makedirs(db_dir, exist_ok=True)

db_path = os.path.join(db_dir, 'db-intimacoes.db')

automation.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
automation.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(automation)

token = "jrs-start"

@automation.route('/automacao/cadastro/intimacoes/api/', methods=['POST'])
def executar_automacao():
    try:
        print('🚀 Iniciando automação de protocolo jurídico')

        data = request.get_json()
        token_requests = data.get('token')

        if token_requests != token:
            return jsonify({'status': 'erro', 'mensagem': 'Chave de autenticação inválida'}), 403

        numero_processo = data.get('numero_processo')
        id_processo = data.get('id_processo')

        if not numero_processo:
            return jsonify({'status': 'erro', 'mensagem': 'Erro, número processo inválido'}), 403

        if not id_processo:
            return jsonify({'status': 'erro', 'mensagem': 'Erro, ID processo inválido'}), 403

        # main(numero_processo, id_processo)
        return jsonify({'status': 'ok', 'mensagem': 'Validação concluída com sucesso'})

    except Exception as erro:
        return jsonify({'status': 'erro', 'mensagem': f'Erro ao iniciar automação: {erro}'})
