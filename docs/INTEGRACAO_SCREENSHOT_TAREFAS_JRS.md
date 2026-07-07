# Integração: screenshot da automação de Push na timeline da tarefa

> **Para colar no chat de IA do projeto `tarefas-jrs`.**
> Este documento descreve uma mudança no serviço `api_push_process` (automação de
> Push do PJe) e o que precisa ser feito no `tarefas-jrs` para exibir o print da
> tela ao usuário na timeline da tarefa.

---

## 1. O que mudou no serviço de automação (já implementado)

A automação de Push agora **captura um screenshot da tela** ao final de cada
processamento — tanto em **sucesso/aviso** quanto em **erro** — e o disponibiliza
por URL. Essa URL passou a ser **incluída no webhook de retorno** que o serviço
envia de volta.

- O print é servido pela API Flask do serviço de push na rota
  `GET /screenshots/<arquivo>.png`.
- A URL enviada no retorno é **absoluta** (ex.:
  `http://192.168.11.24:5000/screenshots/0000511-77.2025.5.06.0018_create_ERRO_20260707_181500.png`),
  ou seja, pode ser aberta diretamente no navegador / usada em `<img src>`.

## 2. Novo campo no payload de retorno: `screenshot`

O serviço de push envia o resultado para o `tarefas-jrs` por um `POST`. Existem
dois formatos (contratos). **O campo novo é `screenshot`** e ele é **opcional**:
só aparece quando há um print disponível.

### Contrato A — lista de `callbacks` (formato atual/preferencial)

Quando a mensagem de entrada traz `callbacks`, o serviço faz um `POST` para cada
`url` da lista com o corpo:

```json
{
  "id": 12345,
  "status": "ERRO",
  "token": "abc...",
  "screenshot": "http://192.168.11.24:5000/screenshots/0000511-77.2025.5.06.0018_create_ERRO_20260707_181500.png"
}
```

- `id`      → identificador que o próprio `tarefas-jrs` enviou (ex.: id da tarefa/atividade).
- `status`  → `SUCESSO` | `AVISO` | `ERRO`.
- `token`   → token de autenticação que o `tarefas-jrs` enviou (validar).
- `screenshot` → **NOVO**. URL absoluta do print. **Pode não vir** (campo ausente) se a captura falhar.

### Contrato B — webhook Django legado (fallback)

Quando **não** há `callbacks`, o serviço faz `POST` para o endpoint legado
`/atividades/push/automation/update/status/` com:

```json
{
  "processo": "0000511-77.2025.5.06.0018",
  "status": "ERROR",
  "message": "Nao foi possivel trocar para o perfil 'Advogado'...",
  "screenshot": "http://192.168.11.24:5000/screenshots/..._ERRO_....png"
}
```

- `status` aqui usa o mapeamento legado: `SUCCESS` (sucesso/aviso) ou `ERROR`.
- `screenshot` → **NOVO**, mesma semântica (opcional).

> **Importante:** o campo é **aditivo e retrocompatível**. Integrações que
> ignorarem `screenshot` continuam funcionando sem alteração.

## 3. O que o `tarefas-jrs` precisa fazer

### 3.1 Persistência
1. No endpoint que recebe o retorno da automação (o que hoje trata `id`/`status`
   ou `processo`/`status`/`message`), **ler o campo opcional `screenshot`** do
   corpo do request.
2. Adicionar uma coluna/campo `screenshot_url` (`TEXT`/`CharField`, nullable) no
   modelo do **evento da timeline** (ou da atividade de push, conforme o modelo
   existente) e salvar o valor recebido. Se o campo vier ausente/nulo, gravar `null`.

### 3.2 Exibição na timeline
Ao renderizar o evento na timeline da tarefa, quando `screenshot_url` estiver
preenchido, exibir um acesso ao print. Sugestões:

- **Link simples:** `🔍 Ver print da tela` abrindo em nova aba
  (`<a href="{{ screenshot_url }}" target="_blank" rel="noopener">`).
- **Miniatura clicável:** `<a href="{{ screenshot_url }}" target="_blank"><img src="{{ screenshot_url }}" style="max-height:80px;border-radius:6px" alt="print"></a>`.

Exibir tanto em eventos de **erro** (para o usuário entender o que aconteceu na
tela) quanto de **sucesso** (comprovação visual).

### 3.3 Rede / acesso (atenção)
- A URL aponta para o **serviço de push na porta 5000**. Por padrão o host dessa
  URL é o **IP da máquina, detectado automaticamente** pelo serviço em runtime
  (por isso os exemplos acima mostram `192.168.11.24:5000`). Pode ser forçado via
  a env `PUSH_PUBLIC_URL` no serviço de push (ex.: para domínio/reverse-proxy).
- Se a timeline for aberta no **navegador do usuário**, é o **navegador dele** que
  vai buscar a imagem — portanto esse host:porta precisa estar **acessível a
  partir da máquina do usuário** (mesma rede/VPN), não apenas a partir do servidor
  do `tarefas-jrs`.
- Se os usuários acessam de fora da rede onde o `192.168.11.24:5000` é visível,
  há duas opções:
  1. Expor o serviço de push atrás de um domínio/reverse-proxy acessível e ajustar
     `PUSH_PUBLIC_URL` no `.env` do serviço de push; **ou**
  2. O `tarefas-jrs` fazer o download da imagem (server-side, ele consegue
     alcançar `192.168.11.24:5000`) no momento do recebimento do webhook e
     **re-hospedar** o print no próprio storage do `tarefas-jrs`, salvando a URL
     local em `screenshot_url`. Essa opção é a mais robusta para acesso externo.

## 4. Checklist de implementação no `tarefas-jrs`

- [ ] Ler `screenshot` (opcional) no handler do webhook de retorno da automação.
- [ ] Adicionar campo `screenshot_url` (nullable) no modelo do evento/atividade + migração.
- [ ] Salvar o valor no evento correspondente (casar pelo `id`/`processo`).
- [ ] Renderizar link/miniatura na timeline quando `screenshot_url` existir.
- [ ] Validar acesso de rede do navegador do usuário à URL (ou adotar re-hospedagem — seção 3.3).

## 5. Exemplo de handler (pseudo-Django, contrato A)

```python
# view que recebe o POST da automação de push
def receber_status_push(request):
    body = json.loads(request.body)

    atividade_id = body.get("id")
    status       = body.get("status")          # SUCESSO | AVISO | ERRO
    token        = body.get("token")
    screenshot   = body.get("screenshot")       # <-- NOVO (opcional, pode ser None)

    validar_token(token)

    evento = criar_evento_timeline(
        atividade_id=atividade_id,
        status=status,
        screenshot_url=screenshot,   # salvar; renderizar depois se != None
    )
    return JsonResponse({"ok": True})
```
