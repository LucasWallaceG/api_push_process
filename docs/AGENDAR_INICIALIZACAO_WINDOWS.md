# Como iniciar a automação automaticamente no login (Windows)

Este guia mostra como fazer o projeto **api_push_process** iniciar sozinho quando
você (ou a máquina) fizer login no Windows — útil para quando a máquina é
reiniciada e você não está no escritório, ou quando a automação parou por alguma
falha e precisa subir de novo.

Não é preciso saber programar para seguir este passo a passo.

---

## O que vai acontecer

Ao iniciar, o projeto abre **3 janelas** de console, uma para cada serviço:

| Janela | Serviço | O que faz |
|---|---|---|
| 1 | **Dashboard Flask** | Painel web em `http://localhost:5000` |
| 2 | **Consumer Cadastro** | Processa a fila de **cadastro** de push |
| 3 | **Consumer Exclusão** | Processa a fila de **exclusão** de push |

Quem abre essas 3 janelas é o arquivo `start_all.py`. Para não precisar digitar
comandos toda vez, existe um atalho pronto: o arquivo **`iniciar_servicos.bat`**
(na raiz do projeto). É ele que o Agendador de Tarefas vai executar.

> **Antes:** você fazia manualmente: entrar na pasta → ativar o ambiente → `py start_all.py`.
> **Agora:** basta um clique no `.bat` (ou deixar o Agendador rodar sozinho no login).

---

## Parte 1 — Testar o atalho manualmente (faça isto primeiro)

1. Abra a pasta do projeto:
   `d:\OneDrive - jrspericia.com.br\001_Projetos_JRS_Automacoes\api_push_process`
2. Dê **duplo-clique** no arquivo **`iniciar_servicos.bat`**.
3. Devem abrir as **3 janelas** (Dashboard, Cadastro, Exclusão).
   - Deu certo? Ótimo, pode seguir para a Parte 2.
   - Apareceu um erro dizendo que não encontrou o Python (`env`)? Verifique se a
     pasta `env` existe na raiz do projeto. Se não existir, o ambiente virtual
     precisa ser recriado (peça ajuda ao responsável técnico).

---

## Parte 2 — Agendar para iniciar no login

Vamos usar o **Agendador de Tarefas** do Windows.

### Abrir o Agendador
- Aperte a tecla **Windows**, digite **Agendador de Tarefas** e abra.

### Criar a tarefa
1. No menu à direita, clique em **Criar Tarefa…**
   (⚠️ **não** use "Criar Tarefa Básica" — precisamos das opções completas.)

2. **Aba "Geral":**
   - **Nome:** `Iniciar api_push_process`
   - Marque a opção **"Executar somente quando o usuário estiver conectado"**.
     > ⚠️ **Isto é essencial.** É o que faz as 3 janelas aparecerem na sua tela.
     > A outra opção ("Executar estando o usuário conectado ou não") roda tudo
     > escondido, e você não veria nem conseguiria acompanhar os serviços.

3. **Aba "Disparadores"** → botão **"Novo…"**:
   - **Iniciar a tarefa:** `Ao fazer logon`
   - **Usuário específico:** selecione o seu usuário.
   - Marque **"Atrasar tarefa por:"** e escolha **1 minuto**.
     > Isso dá tempo para a **rede** (RabbitMQ) e o **OneDrive** ficarem prontos
     > depois que o Windows inicia. Se ainda falhar, aumente para 2 ou 3 minutos.
   - Clique **OK**.

4. **Aba "Ações"** → botão **"Novo…"**:
   - **Ação:** `Iniciar um programa`
   - **Programa/script:** (copie e cole exatamente)
     ```
     d:\OneDrive - jrspericia.com.br\001_Projetos_JRS_Automacoes\api_push_process\iniciar_servicos.bat
     ```
   - **Iniciar em (opcional):** (copie e cole — **sem aspas**)
     ```
     d:\OneDrive - jrspericia.com.br\001_Projetos_JRS_Automacoes\api_push_process
     ```
   - Clique **OK**.

5. **Aba "Condições":**
   - **Desmarque** "Iniciar a tarefa somente se o computador estiver ligado na
     rede elétrica" (importante se for notebook, para funcionar na bateria).

6. Clique **OK** para salvar a tarefa (o Windows pode pedir a sua senha).

### Testar a tarefa
- Na lista do Agendador, clique com o **botão direito** na tarefa
  `Iniciar api_push_process` → **Executar**.
- As **3 janelas** devem abrir. Se abrirem, está tudo certo: a partir do próximo
  login, elas subirão sozinhas.

---

## Cuidados importantes

| Situação | O que saber / fazer |
|---|---|
| **Máquina reinicia e fica na tela de senha** | A tarefa só roda **depois que alguém fizer login**. Para subir sozinho após um reboot sem ninguém presente, é preciso configurar o **logon automático do Windows** (peça ao responsável de TI). |
| **Rede/RabbitMQ ainda não pronta no login** | A janela do consumer mostra um erro de conexão. O **atraso de 1 minuto** no disparo ajuda; se persistir, aumente o atraso na aba Disparadores. |
| **Arquivos "só na nuvem" (OneDrive)** | Clique com o botão direito na pasta do projeto → **"Sempre manter neste dispositivo"**. Assim os arquivos estão sempre disponíveis no login. |
| **Quero parar os serviços** | Basta fechar as 3 janelas de console. |
| **Quero desligar o início automático** | No Agendador de Tarefas, clique com o botão direito na tarefa → **Desabilitar** (ou **Excluir**). |

---

## Resumo rápido

1. `iniciar_servicos.bat` (na raiz do projeto) abre os 3 serviços de uma vez.
2. No **Agendador de Tarefas**, crie uma tarefa que roda esse `.bat` **ao fazer logon**,
   com **"Executar somente quando o usuário estiver conectado"** marcado e um
   **atraso de 1 minuto**.
3. Teste com botão direito → **Executar** antes de confiar no automático.
