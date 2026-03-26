# Contexto do projeto — Automação (Flask)

## Visão geral da arquitetura

Este projeto faz parte de uma arquitetura orientada a eventos composta por dois serviços independentes:

| Serviço | Stack | Repositório |
|---|---|---|
| **Sistema web** | Django | repositório separado |
| **Automação** | Flask | este repositório |

A comunicação entre eles usa **RabbitMQ** como broker de mensagens e um **webhook HTTP** para o retorno do resultado.

---

## Fluxo completo

```
[Django] publica JSON na fila RabbitMQ (fila_entrada)
              │
         [Flask worker] ← consome da fila  ← AQUI começa este serviço
              │
         executa a automação
              │
         POST /webhook/retorno/ → [Django]
              │
         Django atualiza o banco (status=SUCESSO ou ERRO)
```

---

## Responsabilidades deste serviço (Flask)

1. **Monitorar a fila** `fila_entrada` do RabbitMQ continuamente.
2. **Consumir a mensagem** e extrair o payload + `id` da instância Django.
3. **Executar a automação** e determinar se o resultado é `SUCESSO` ou `ERRO`.
4. **Chamar o webhook** `POST /webhook/retorno/` no Django com o resultado.
5. Fazer `ack` da mensagem **somente após** o webhook ser disparado com sucesso.

---

## Contrato da mensagem consumida da fila (fila_entrada)

```json
{
  "id": 42,
  "token": "SEU_TOKEN_SECRETO",
  // ...demais campos do payload da operação
}
```

- `id` é a PK da instância no banco Django — deve ser enviado de volta no webhook.
- A fila é declarada com `durable=True`. Usar `basic_qos(prefetch_count=1)` para processar uma mensagem por vez.
- Usar `ack` manual (`auto_ack=False`) para garantir reprocessamento em caso de falha.

---

## Contrato do webhook de retorno (enviado pelo Flask)

**Endpoint do Django:** `POST http://django-host/webhook/retorno/`

**Body a enviar:**
```json
{
  "id": 42,
  "status": "SUCESSO",
  "token": "SEU_TOKEN_SECRETO"
}
```

- `status` deve ser exatamente `"SUCESSO"` ou `"ERRO"`.
- O `token` é validado pelo Django — sem ele a requisição é rejeitada com 403.

---

## Referência de implementação

### Consumer da fila
```python
import pika, json, requests

DJANGO_WEBHOOK_URL = "http://django-host/webhook/retorno/"
TOKEN = "SEU_TOKEN_SECRETO"
RABBITMQ_URL = "amqp://localhost"

def executar_automacao(payload: dict) -> bool:
    """
    Implementar aqui a lógica da automação.
    Retorna True se bem-sucedido, False caso contrário.
    """
    raise NotImplementedError

def finalizar(id_instancia: int, sucesso: bool):
    status = "SUCESSO" if sucesso else "ERRO"
    requests.post(
        DJANGO_WEBHOOK_URL,
        json={"id": id_instancia, "status": status, "token": TOKEN},
        timeout=10,
    )

def callback(ch, method, properties, body):
    data = json.loads(body)
    try:
        sucesso = executar_automacao(data)
        finalizar(data["id"], sucesso)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"Erro ao processar mensagem: {e}")
        finalizar(data["id"], sucesso=False)
        ch.basic_ack(delivery_tag=method.delivery_tag)  # ack mesmo no erro para não travar a fila

def iniciar_consumer():
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue="fila_entrada", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="fila_entrada", on_message_callback=callback)
    print("Aguardando mensagens em fila_entrada...")
    channel.start_consuming()

if __name__ == "__main__":
    iniciar_consumer()
```

---

## Dependências relevantes
- `pika` — cliente RabbitMQ para Python
- `requests` — para chamar o webhook Django
- RabbitMQ rodando em `amqp://localhost` (ajustar para o ambiente real)

---

## O que este serviço NÃO faz
- Não expõe rotas HTTP para o frontend (o Flask aqui é só um worker, não um servidor web público).
- Não publica em nenhuma fila de retorno — usa webhook direto.
- Não acessa o banco de dados Django diretamente.
