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
Para rodar o projeto completo (API + Worker), execute o arquivo principal:

Bash
python main.py
Simulando um envio de dados (Postman/cURL):
Bash
curl -X POST http://localhost:5000/push/received \
     -H "Content-Type: application/json" \
     -d '{
           "numero_processo": "0000000-00.2000.5.06.0011",
           "tribunal": "6",
           "acao": "create"
         }'
📝 Padrões de Projeto Aplicados
Page Object Model (POM): Organização da automação web por páginas.

Singleton: Gerenciamento de conexões únicas com o RabbitMQ.

Facade: Simplificação das chamadas complexas de automação para a API.