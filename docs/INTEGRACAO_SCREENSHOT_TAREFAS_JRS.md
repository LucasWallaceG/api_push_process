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
  "id": "ca53bfff-b8e5-4ab2-9776-3bbdead6113f",
  "status": "SUCESSO",
  "message": "o processo 0000387-04.2026.5.13.0006 já está cadastrado no push.",
  "token": "6c5c7369c87a1a7d478b7679248b75f729db27e45eafb388",
  "screenshot": "http://192.168.11.24:5000/screenshots/0000387-04.2026.5.13.0006_create_SUCESSO_20260707_181500.png"
}
```

- `id`      → identificador que o próprio `tarefas-jrs` enviou (ex.: id da tarefa/atividade).
- `status`  → `SUCESSO` | `AVISO` | `ERRO`.
- `message` → **NOVO**. A **mensagem real** devolvida pelo PJe após a ação (ex.:
  "já está cadastrado no push.", "cadastrado com sucesso", detalhe do erro). É o
  texto que deve ser exibido ao usuário na timeline. Pode vir em minúsculas.
- `token`   → token de autenticação que o `tarefas-jrs` enviou (validar).
- `screenshot` → URL absoluta do print. **Pode não vir** (campo ausente) se a captura falhar.

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
1. No endpoint que recebe o retorno da automação, **ler os campos** do corpo:
   `status`, **`message`** (a mensagem real do PJe) e o opcional `screenshot`.
2. Adicionar/usar campos no modelo do **evento da timeline** (ou da atividade de
   push): um para a mensagem (ex.: `mensagem`/`descricao`, `TEXT`) e
   `screenshot_url` (`TEXT`/`CharField`, nullable). Salvar os valores recebidos;
   se `screenshot` vier ausente/nulo, gravar `null`.

### 3.2 Exibição na timeline (mensagem transparente)
O objetivo é que o usuário **entenda exatamente o que aconteceu**, sem mensagens
genéricas. Regras de apresentação:

1. **Exibir a `message` literal do retorno** como texto principal do evento — é o
   feedback real do PJe (ex.: *"o processo 0000387-04.2026.5.13.0006 já está
   cadastrado no push."*). **Não** substituir por texto genérico do tipo
   "Concluído" / "Erro".
   - A mensagem pode vir em minúsculas; se quiser, aplique só um *capitalize* na
     primeira letra para leitura, **sem** alterar o conteúdo.
2. **Combinar com o `status`** para dar cor/ícone ao evento, mantendo a mensagem:
   - `SUCESSO` → ✅ verde + a `message`.
   - `AVISO`   → ⚠️ amarelo + a `message` (ex.: já cadastrado).
   - `ERRO`    → ❌ vermelho + a `message` (detalhe do que falhou).
3. **Anexar o print** quando `screenshot_url` existir — tanto em erro (entender o
   que apareceu na tela) quanto em sucesso (comprovação visual):
   - **Link simples:** `🔍 Ver print da tela` em nova aba
     (`<a href="{{ screenshot_url }}" target="_blank" rel="noopener">`).
   - **Miniatura clicável:** `<a href="{{ screenshot_url }}" target="_blank"><img src="{{ screenshot_url }}" style="max-height:80px;border-radius:6px" alt="print"></a>`.

**Exemplo de card na timeline:**

```
✅  Cadastro no Push — 07/07/2026 18:15
    o processo 0000387-04.2026.5.13.0006 já está cadastrado no push.
    🔍 Ver print da tela
```

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

- [ ] Ler `message` (mensagem real) e `screenshot` (opcional) no handler do webhook.
- [ ] Persistir a `message` no evento da timeline (campo de texto) + `screenshot_url` (nullable) + migração.
- [ ] Salvar os valores no evento correspondente (casar pelo `id`/`processo`).
- [ ] Renderizar a `message` literal como texto do evento (não usar texto genérico), com cor/ícone pelo `status`.
- [ ] Renderizar link/miniatura do print quando `screenshot_url` existir.
- [ ] Validar acesso de rede do navegador do usuário à URL (ou adotar re-hospedagem — seção 3.3).

## 5. Exemplo de handler (pseudo-Django, contrato A)

```python
# view que recebe o POST da automação de push
def receber_status_push(request):
    body = json.loads(request.body)

    atividade_id = body.get("id")
    status       = body.get("status")           # SUCESSO | AVISO | ERRO
    message      = body.get("message", "")       # <-- NOVO: mensagem real do PJe
    token        = body.get("token")
    screenshot   = body.get("screenshot")        # opcional, pode ser None

    validar_token(token)

    evento = criar_evento_timeline(
        atividade_id=atividade_id,
        status=status,
        mensagem=message,            # exibir literal na timeline (não trocar por texto genérico)
        screenshot_url=screenshot,   # salvar; renderizar link/miniatura se != None
    )
    return JsonResponse({"ok": True})
```
