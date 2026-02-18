from flask import Flask, jsonify, request

app = Flask(__name__)

# Nosso "banco de dados" temporário
produtos = [
    {
        "numero_processo": "0000000-00.2000.5.06.0011",
        "tribunal": "6",
        "grau": "1",
        "acao": "delete",
        "pagina": "10",
    },
    {
        "numero_processo": "0000000-00.2000.5.10.0011",
        "tribunal": "10",
        "grau": "2",
        "acao": "create",
        "pagina": "5",
    }
]

# Rota para COLETAR dados (GET)
@app.route('/push/received', methods=['GET'])
def listar_produtos():
    return jsonify(produtos), 200

# Rota para ENVIAR dados (POST)
@app.route('/push/received', methods=['POST'])
def adicionar_produto():
    novo_produto = request.get_json()
    produtos.append(novo_produto)

    
    return jsonify({"mensagem": "Produto adicionado com sucesso!", "item": novo_produto}), 201

if __name__ == '__main__':
    app.run(debug=True)