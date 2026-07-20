🤖 Automation Bridge: API & RPA Orchestrator
Este projeto é um ecossistema de automação que integra uma API Flask para recepção de dados, RabbitMQ para mensageria e orquestração de tarefas, e robôs desenvolvidos com Selenium e PyAutoGUI para processamento de dados com Pandas.

A arquitetura foi desenhada seguindo o padrão Producer-Consumer, garantindo escalabilidade e resiliência no processamento de fluxos web e desktop.

🏗️ Arquitetura do Projeto
O fluxo de dados segue o seguinte caminho:

Sistema Externo envia um JSON via POST para a API Flask.

API (Producer) valida os dados e os encaminha para uma fila no RabbitMQ.

Worker (Consumer) escuta a fila em tempo real.

Automação processa os dados usando:

Pandas: Limpeza e manipulação de DataFrames.

Selenium: Automação de sistemas Web (Browser).

PyAutoGUI: Interação com interfaces Desktop/Legado.

📁 Estrutura de Pastas
Plaintext
meu_projeto/
├── app/
│   ├── core/           # Configurações de infraestrutura (RabbitMQ, Logs)
│   ├── automation/     # Lógica dos robôs (Web/Page Objects e Desktop)
│   ├── services/       # API Flask e Clientes de integração
│   └── tasks/          # Workers que consomem a fila
├── data/               # Arquivos temporários (CSV, XLSX)
├── main.py             # Ponto de entrada que orquestra os serviços
└── requirements.txt    # Dependências do projeto
🚀 Tecnologias Utilizadas
Python 3.10+

Flask: Interface de recebimento de dados (API).

RabbitMQ: Message Broker para gerenciamento de filas.

Selenium: Automação de processos via navegador.

PyAutoGUI: Automação de interface desktop (RPA).

Pandas: Processamento e análise de dados.

🛠️ Configuração e Instalação
1. Pré-requisitos
Python instalado.

Servidor RabbitMQ rodando (Local ou Docker).

2. Instalação
Bash
# Clone o repositório
git clone https://github.com/seu-usuario/seu-projeto.git

# Entre na pasta
cd seu-projeto

# Crie um ambiente virtual
python -m venv venv

# Ative o ambiente
# No Windows:
venv\Scripts\activate
# No Linux/Mac:
source venv/bin/activate

# Instale as dependências
pip install -r requirements.txt
🚦 Como Executar

**Recomendado — iniciar todos os serviços de uma vez:**
```bash
python start_all.py
```
Abre automaticamente três terminais separados:

| Terminal | Serviço | Detalhe |
|---|---|---|
| 1 | Dashboard Flask | `http://localhost:8000` |
| 2 | Consumer Cadastro | fila `queue_push_insert` |
| 3 | Consumer Exclusão | fila `queue_push_delete` |

---

**Execução individual (opcional):**
```bash
# Somente o dashboard visual (Flask)
python main.py

# Somente o consumer de cadastros
python consumer_cadastrar_push.py

# Somente o consumer de exclusões
python consumer_excluir_push.py
```

> Cada consumer pode ser executado em máquinas separadas para escalar o processamento em lote.

---

**Simulando um envio de dados (Postman/cURL):**
```bash
curl -X POST http://localhost:8000/push/received \
     -H "Content-Type: application/json" \
     -d '{
           "numero_processo": "0000000-00.2000.5.06.0011",
           "tribunal": "6",
           "acao": "create"
         }'
```
📸 Screenshots da Automação

A cada processamento (cadastro ou exclusão de push), a automação captura um
**print da tela** — tanto em **sucesso/aviso** quanto em **erro** — vinculado ao
número do processo. Os prints:

- São salvos em `screenshots/` (criada automaticamente; ignorada pelo Git).
- Ficam disponíveis por URL na rota `GET /screenshots/<arquivo>.png`.
- Aparecem na coluna **"Print"** do dashboard (link "🔍 Ver").
- Têm a **URL absoluta incluída no webhook de retorno** (campo `screenshot`),
  para que sistemas externos (ex.: `tarefas-jrs`) exibam o print na timeline da
  tarefa. Ver [`docs/INTEGRACAO_SCREENSHOT_TAREFAS_JRS.md`](docs/INTEGRACAO_SCREENSHOT_TAREFAS_JRS.md).

⚙️ Variáveis de Ambiente (`.env`)

Além das configurações do RabbitMQ, o serviço usa:

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `PORT` | Não | `8000` | Porta em que a API Flask (dashboard + endpoints) escuta. ⚠️ Evite portas bloqueadas pelos navegadores (`ERR_UNSAFE_PORT`) — a mais comum é a **6000** (X11); veja abaixo. |
| `API_BASE_URL` | Não | `http://192.168.11.3:5005` | Base do **webhook Django legado**, usado **apenas** quando a mensagem não traz `callbacks`. ⚠️ Não aponte para a porta do `PORT` — seria auto-referência a este próprio serviço. |

> **Portas bloqueadas pelo navegador:** Chrome e Firefox recusam certas portas por
> segurança (erro `ERR_UNSAFE_PORT`), mesmo com o servidor rodando normalmente.
> As mais comuns na lista: **6000** (X11), 6665–6669 (IRC), 2049, 4045, 5060, 6566, 10080.
> Portas seguras e usuais: **8000, 8080, 5000, 5050, 8888**.
| `PUSH_PUBLIC_URL` | Não | *(auto)* | URL base pública deste serviço, usada para montar a **URL absoluta** dos screenshots no webhook de retorno. **Se não definida, o IP da máquina é detectado automaticamente em runtime** — roda em qualquer IP sem configurar nada. Defina apenas para forçar um host/domínio específico (ex.: atrás de reverse-proxy ou acesso externo por domínio): `PUSH_PUBLIC_URL=http://meu-dominio:8000`. |
| `PUSH_PUBLIC_PORT` | Não | valor de `PORT` | Porta usada na detecção automática do IP (ignorada se `PUSH_PUBLIC_URL` estiver definida). Só defina se a porta pública for diferente da porta em que o Flask escuta (ex.: atrás de proxy). |

> **Atenção (rede):** a URL do screenshot aponta para este serviço (porta `8000` por padrão).
> Como é o **navegador do usuário** que abre a imagem na timeline do `tarefas-jrs`,
> esse host:porta precisa estar acessível a partir da máquina do usuário. Para
> acesso externo, exponha o serviço por um domínio/reverse-proxy e defina
> `PUSH_PUBLIC_URL`, ou faça o `tarefas-jrs` re-hospedar o print (ver doc de integração).

📝 Padrões de Projeto Aplicados
Page Object Model (POM): Organização da automação web por páginas.

Singleton: Gerenciamento de conexões únicas com o RabbitMQ.

Facade: Simplificação das chamadas complexas de automação para a API.