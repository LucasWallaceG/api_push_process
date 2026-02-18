import os
import json
import requests


def enviar_json_push(dados_json, base_url="http://192.168.11.24:8000"):
    """
    Envia a lista de processos (JSON) para a rota de sincronização do PUSH.

    Args:
        dados_json (list): Lista de dicionários contendo os dados (formato da sua automação).
                           Ex: [{'numero_processo': '...', 'tribunal': 'TRT1', ...}]
        base_url (str): URL base do servidor. Padrão: http://192.168.11.24:8000
    """
    # Rota configurada em apppush_visualizar/urls.py e incluída via taskmanager/urls.py
    endpoint = f"{base_url.rstrip('/')}/atividades/sync/json/"

    headers = {
        'Content-Type': 'application/json'
    }

    print(f"🚀 Iniciando envio de {len(dados_json)} registros para: {endpoint}")

    try:
        # O endpoint aceita o JSON direto no corpo da requisição (raw body)
        response = requests.post(endpoint, json=dados_json, headers=headers, timeout=60)

        if response.status_code == 200:
            resultado = response.json()
            if resultado.get('status') == 'success':
                print("✅ Sincronização concluída com sucesso!")
                detalhes = resultado.get('details', {})
                print(f"   - Processados: {detalhes.get('processed')}")
                print(f"   - Criados (Novos): {detalhes.get('created')}")
                print(f"   - Atualizados: {detalhes.get('updated')}")

                erros = detalhes.get('errors', [])
                if erros:
                    print(f"\n⚠️  Atenção: {len(erros)} itens não puderam ser processados:")
                    for erro in erros[:5]:  # Mostra os 5 primeiros erros
                        print(f"   - {erro}")
                    if len(erros) > 5:
                        print(f"   - ... e mais {len(erros) - 5} erros.")
            else:
                print(f"⚠️  O servidor retornou sucesso mas com aviso: {resultado.get('message')}")

        else:
            print(f"❌ Erro na requisição: HTTP {response.status_code}")
            try:
                print(f"   Detalhe: {response.json().get('message')}")
            except:
                print(f"   Conteúdo: {response.text[:200]}")

    except requests.exceptions.ConnectionError:
        print(f"❌ Falha de Conexão: Verifique se o servidor ({base_url}) está acessível.")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")


# --- Exemplo de como chamar na sua automação ---
if __name__ == "__main__":
    # Exemplo do JSON que sua automação gera

    # 1. Se quiser enviar a variável 'meu_json' que você criou no código:
    # enviar_json_push(meu_json)

    # 2. Se quiser ler do arquivo (Recomendado para produção):
    caminho_arquivo = fr'{os.getcwd()}\processos_push_2026-01-24.json'

    if os.path.exists(caminho_arquivo):
        print(f"Lendo arquivo: {caminho_arquivo}")
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            dados_carregados = json.load(f)  # <--- Converte o arquivo em Lista Python

        enviar_json_push(dados_carregados)  # <--- Envia a LISTA, não o caminho
    else:
        print("Arquivo JSON não encontrado.")
