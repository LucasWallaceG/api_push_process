meu_projeto/
│
├── app/
│   ├── __init__.py
│   ├── core/              # Configurações centrais (RabbitMQ, DB, Logs)
│   │   ├── config.py
│   │   └── rabbitmq.py     # Lógica de conexão/consumo do Rabbit
│   │
│   ├── automation/        # O "coração" da automação
│   │   ├── web/           # Selenium (Page Objects)
│   │   │   ├── pages/     # Classes representando páginas web
│   │   │   └── browser.py # Setup do WebDriver
│   │   └── desktop/       # PyAutoGUI (Ações em sistemas legados)
│   │       └── actions.py
│   │
│   ├── services/          # Lógica de negócio e Integrações API
│   │   ├── api_client.py   # Requisições HTTP (Requests/Aiohttp)
│   │   └── data_service.py # Manipulação com Pandas
│   │
│   └── tasks/             # Fluxos de trabalho (Orquestração)
│       └── worker.py       # Onde o RabbitMQ chama as funções
│
├── data/                  # Arquivos locais (CSV, Excel, JSON)
│   ├── input/
│   └── output/
│
├── logs/                  # Logs de execução
├── tests/                 # Testes unitários e de integração
├── .env                   # Variáveis de ambiente (Senhas, URLs)
├── requirements.txt
└── main.py                # Ponto de entrada da aplicação