import time
import os, re
import requests
import pyautogui
from datetime import datetime
from selenium import webdriver
from pywinauto.mouse import click
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from pywinauto import Desktop, timings, keyboard
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
)
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions



# !! IMPORTANTE !!:
# Se clonou o projeto do zero, é necessário criar o bando de dados local da automação
# Execute no terminal o script (init_db.py): "python init_db.py"

HOST_REMOTO_CHAT_LOG = "192.168.11.24"
HOST_REMOTO_ADD_NEWS_INTIMACOES = "192.168.11.24:8000"
MAPEAMENTO_CERTIFICADOS = {
    "roberto":  "JOSE ROBERTO DOS SANTOS JUNIOR",
    "paula": "ANA PAULA PEDROSA COELHO",
    "marcos":   "MARCOS AURELIO BRITO DOS SANT",
}
MAP_IMG_CERTIFICADO = {
    "roberto": "cert_roberto.png",
    "marcos":  "cert_marcos.png",
    "paula":   "cert_paula.png",
}


def to_date_or_none(value):
    if not value or value == "-" or value == "":
        return None

    try:
        # aceita dd/mm/yyyy
        if "/" in value:
            return datetime.strptime(value, "%d/%m/%Y").date()

        # aceita yyyy-mm-dd
        return datetime.strptime(value, "%Y-%m-%d").date()
    except:
        return None


def sincronizar_sqlite(perito_id, trt):
    url = f"http://{HOST_REMOTO_ADD_NEWS_INTIMACOES}/atividades/intimacoes/api/snapshot/?perito_id={perito_id}&trt={trt}"

    resp = requests.get(url).json()
    intimacoes_web = resp["intimacoes"]

    print(f"🔄 Sincronizando SQLite... total {len(intimacoes_web)} registros")

    # Limpa tabela local
    Intimacoes.query.delete()
    db.session.commit()

    # Recria tudo no SQLite
    for item in intimacoes_web:
        nova = Intimacoes(
            numero_processo=item["numero_processo"],
            data_intimacao_real=item["data_intimacao_real"],
            data_intimacao=to_date_or_none(item["data_intimacao"]),
            tipo_acao=item["tipo_acao"],
            situacao=item["situacao"],
            trt=item["trt_id"],
            perfil=item["perfil"],
        )
        db.session.add(nova)

    db.session.commit()
    print("✅ Sincronização concluída.")


def sincronizar_uma_vez(perito, trt):
    """
    Executa a sincronização apenas uma vez por PERITO + TRT.
    """
    # Normaliza nome para arquivos (ex: roberto → roberto.lock)
    perito_norm = str(perito).replace(" ", "_").lower()
    lock_file = f"sync_{perito_norm}_{trt}.lock"

    if os.path.exists(lock_file):
        print(f"🔒 Sincronização já foi feita para {perito} / TRT {trt}. Pulando.")
        return

    # Sincroniza agora
    print(f"🚀 Executando sincronização inicial para {perito} / TRT {trt} ...")
    sincronizar_sqlite(perito, trt)

    # Marca como sincronizado
    with open(lock_file, "w") as f:
        f.write("done")

    print(f"🔒 Sincronização marcada para {perito} / TRT {trt}.")


def marcar_execucao(perito_id, trt):
    try:
        url = f"http://{HOST_REMOTO_ADD_NEWS_INTIMACOES}/atividades/intimacoes/api/execucao/"
        payload = {"perito_id": perito_id, "trt": trt}
        print(f"⏱ Registrando execução para Perito {perito_id} | TRT {trt}")
        requests.post(url, json=payload, timeout=10, proxies={"http": None, "https": None})
    except Exception as e:
        print(f"❌ Erro ao registrar execução: {e}")


def send_data_ws(mensagem, trt=None, status=None, intimacoes=None):
    try:
        url = fr"http://{HOST_REMOTO_CHAT_LOG}:9000/api/websocket/logs/intimacoes/"
        return

        payload = {
            "mensagem": mensagem,
            "trt": trt,
        }

        if status:
            payload["status"] = status

        if intimacoes:
            payload["intimacoes"] = intimacoes

        response = requests.post(url, json=payload)
        response.raise_for_status()

    except requests.exceptions.RequestException as erro:
        print(f"❌ Erro ao enviar log via POST: {erro}")


def send_intimacoes_api(intimacoes, perito_id):
    # url = "http://www.jrsforms-teste.com.br/atividades/intimacoes/api/save/"
    # url = "http://www.jrsformularios.com/atividades/intimacoes/api/save/"
    url = fr"http://{HOST_REMOTO_ADD_NEWS_INTIMACOES}/atividades/intimacoes/api/save/"
    headers = {"Content-Type": "application/json"}
    payload = {"intimacoes": intimacoes, "perito_id": perito_id}

    try:
        print(f'🚀 Enviando {len(intimacoes)} intimações para a API...')
        proxies = {"http": None, "https": None}
        response = requests.post(url, headers=headers, json=payload, timeout=30, proxies=proxies)

        if response.status_code == 200:
            print("✅ Envio realizado com sucesso.")
            print("🔁 Resposta:", response.json())
            return True
        else:
            print(f"❌ Falha no envio. Status: {response.status_code}")
            print("🧾 Resposta:", response.text)
            return False
    except requests.exceptions.RequestException as erro:
        print(f"❌ Erro de conexão: {erro}")
        return False


def criar_driver(perfil_nome=None):
    options = FirefoxOptions()

    # 🔒 Perfil FIXO por servico — persiste as escolhas ("lembrar minha escolha")
    # entre execucoes, evitando o pop-up de permissao do certificado a cada run.
    # ⚠️ O Firefox NAO permite 2 processos no mesmo perfil simultaneamente, e este
    # projeto roda 2 consumers em paralelo (cadastro/exclusao). Por isso cada
    # servico usa um perfil proprio, definido pela env FIREFOX_PROFILE.
    if not perfil_nome:
        perfil_nome = os.getenv("FIREFOX_PROFILE", "default")
    perfil_dir = os.path.abspath(os.path.join("firefox_profiles", perfil_nome))
    os.makedirs(perfil_dir, exist_ok=True)
    options.add_argument("-profile")
    options.add_argument(perfil_dir)

    # Dispensa o pop-up de permissao para abrir o app externo do
    # certificado/assinador (ex.: "sso.cloud.pje.jus.br quer acessar...").
    options.set_preference("security.external_protocol_requires_permission", False)
    options.set_preference("network.protocol-handler.external-default", True)
    options.set_preference("network.protocol-handler.warn-external-default", False)

    caminho_driver = os.path.abspath("./app/automation/drivers/geckodriver.exe")
    print(f'- (Path Geckodriver): {caminho_driver}')
    print(f'- (Firefox profile): {perfil_dir}')
    service = FirefoxService(executable_path=caminho_driver)
    driver = webdriver.Firefox(service=service, options=options)
    driver.maximize_window()
    return driver


def abrir_pje(driver, trt, grau="primeirograu"):
    time.sleep(3)
    try:
        url = f"https://pje.trt{trt}.jus.br/{grau}/login.seam"
        mensagem = f"🌐 Acessando URL: {url}"
        print(mensagem)
        

        driver.get(url)
        return driver
    except Exception as e:
        mensagem = f'❌ Erro ao acessar TRT-{trt}: {e}'
        print(mensagem)
        
        return None


def clicar_botao_pdpj(driver, timeout=20):
    try:
        wait = WebDriverWait(driver, timeout)

        # 1️⃣ Aguarda o botão existir no DOM
        botao = wait.until(
            EC.presence_of_element_located((By.ID, "btnSsoPdpj"))
        )

        # 2️⃣ Scroll até o botão (muito importante)
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", botao
        )
        time.sleep(0.3)

        # 3️⃣ Aguarda ficar clicável
        wait.until(EC.element_to_be_clickable((By.ID, "btnSsoPdpj")))

        try:
            # 4️⃣ Clique normal
            botao.click()
        except ElementClickInterceptedException:
            # 5️⃣ Fallback: clique via JS
            driver.execute_script("arguments[0].click();", botao)

        mensagem = "✅ Botão PDPJ clicado com sucesso."
        print(mensagem)
        
        return True

    except TimeoutException:
        mensagem = "❌ Botão PDPJ não ficou disponível a tempo."
        print(mensagem)
        
        return None

    except Exception as erro:
        mensagem = f"❌ Erro ao clicar no botão PDPJ: {erro}"
        print(mensagem)
        
        return None


def clicar_botao_pdpj_v0(driver):
    time.sleep(3)
    try:
        wait = WebDriverWait(driver, 15)
        botao = wait.until(EC.element_to_be_clickable((By.ID, "btnSsoPdpj")))
        botao.click()

        mensagem = "✅ Botão PDPJ clicado com sucesso."
        
        return True

    except Exception as erro:
        mensagem = f"❌ Erro ao clicar no botão PDPJ: {erro}"
        print(mensagem)
        
        return None


def clicar_certificado_digital(driver):
    time.sleep(3)
    try:
        wait = WebDriverWait(driver, 15)
        link_xpath = "//a[.//span[contains(text(), 'Seu certificado digital')]]"

        wait.until(EC.presence_of_element_located((By.XPATH, link_xpath)))
        link = driver.find_element(By.XPATH, link_xpath)

        driver.execute_script("arguments[0].click();", link)
        mensagem = "✅ Certificado digital clicado com sucesso."
        
        return True

    except Exception as erro:
        mensagem = f"❌ Erro ao clicar no certificado digital: {erro}"
        print(mensagem)
        
        return False


def _selecionar_e_clicar(dlg, num_setas_baixo, coords_clique):
    """
    Função auxiliar que executa as ações de teclado e o clique do mouse.
    """
    # Etapa de navegação com TAB (comum a todos)
    print("⌨️ Pressionando TAB 3 vezes para chegar na lista...")
    keyboard.send_keys('{TAB 3}')
    time.sleep(0.5)

    # Etapa de seleção com SETA PARA BAIXO (varia por perito)
    if num_setas_baixo > 0:
        print(f"⌨️ Pressionando SETA PARA BAIXO {num_setas_baixo} vez(es)...")
        # Envia a tecla 'DOWN' o número de vezes especificado
        keyboard.send_keys(f'{{DOWN {num_setas_baixo}}}')
        time.sleep(1)

    print("✅ Certificado selecionado na lista.")

    # Etapa de clique por coordenada (varia por perito)
    print("🖱️ Calculando posição do botão 'OK' e clicando...")
    rect = dlg.rectangle()

    # Usa as coordenadas recebidas como parâmetro
    ok_x = rect.right - coords_clique['x_offset']
    ok_y = rect.bottom - coords_clique['y_offset']

    print(f"Posição da janela: Direita={rect.right}, Fundo={rect.bottom}")
    print(f"Coordenada calculada para o clique: X={ok_x}, Y={ok_y}")
    click(coords=(ok_x, ok_y))


def localizar_img(imagem):
    max_espera = 40
    contador = 0
    img_nome = os.path.basename(imagem)

    print(f"- [LOCALIZANDO_IMG] Buscando '{img_nome}'...")

    for _ in range(3):
        try:
            while True:
                pos = pyautogui.locateOnScreen(imagem, grayscale=True, confidence=0.88)

                if pos:
                    print(f"- [OK] Imagem '{img_nome}' localizada!")
                    return pos

                time.sleep(1)
                contador += 1

                if contador >= max_espera:
                    print(f"- [ERRO] Imagem '{img_nome}' não encontrada no tempo limite.")
                    return 1

        except Exception as e:
            print(f"- [EXCEPT localizar_img] {e}")
            time.sleep(1)

    print("- [FALHA] Não foi possível localizar a imagem.")
    return 1


def duplo_click_certificado(local_img):
    for _ in range(3):
        pos = localizar_img(local_img)

        if pos != 1:
            centro = pyautogui.center(pos)
            pyautogui.doubleClick(centro)
            print("- [OK] Duplo clique realizado no certificado.")
            return [True, ""]

        time.sleep(1)

    msg = "[ERRO] Falha ao clicar no certificado."
    print(msg)
    return [False, msg]


def preencher_senha_desktop(perito: str):
    """
    Seleciona o certificado correto usando reconhecimento de imagem,
    baseado no perito atual.
    """

    perito = perito.lower()

    if perito not in MAP_IMG_CERTIFICADO:
        print(f"❌ Perito '{perito}' não mapeado para uma imagem de certificado.")
        return False

    nome_imagem = MAP_IMG_CERTIFICADO[perito]
    # local_img = os.path.join(os.getcwd(), "images", nome_imagem)
    subdir = r"app\automation\images"
    local_img = os.path.join(os.getcwd(), subdir, nome_imagem)
    print(f'- (Subdir): {subdir}')
    print(f'- (DirFull): {local_img}')

    print(f"▶ Selecionando certificado para: {perito.upper()}")
    print(f"📄 Imagem usada: {local_img}")

    try:
        # Detecta a janela
        padrao = re.compile(r"Seleção de certificado", re.I)
        dlg = Desktop(backend="uia").window(title_re=padrao).wait("visible", timeout=20)
        dlg.set_focus()
        time.sleep(1)

        print("🔍 Procurando imagem do certificado...")

        resultado = duplo_click_certificado(local_img)

        if resultado[0]:
            print("🎉 Certificado selecionado com sucesso!")

            nome_imagem = "btn_ok.png"
            # local_img = os.path.join(os.getcwd(), "images", nome_imagem)
            subdir = r"app\automation\images"
            local_img = os.path.join(os.getcwd(), subdir, nome_imagem)
            print(f'- (Subdir): {subdir}')
            print(f'- (DirFull): {local_img}')
            
            resultado_2 = duplo_click_certificado(local_img)
            if resultado_2[0]:
                print('🎉 Clique no botão de confirmação efetuado com sucesso!')
                return True

            return True
        else:
            print("❌ Falha ao clicar no certificado.")
            return False

    except timings.TimeoutError:
        print("❌ A janela de certificado não apareceu.")
        return False

    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False


def gerar_codigo(perito):
    time.sleep(3)
    url = "http://192.168.11.38:5010/gerador/acesso"

    payload = {
        "token": "jrs-access",
        "perito": str(perito)
    }

    mensagem = f"({perito}) Solicitando codigo de acesso na api"
    
    time.sleep(3)
    try:
        resposta = requests.post(url, json=payload)
        resposta.raise_for_status()

        print("✅ Requisição enviada com sucesso!")
        print("Status:", resposta.status_code)
        print("Resposta JSON:", resposta.json())

        dados = resposta.json()

        if dados.get("status") == "ok" and "codigo_acesso" in dados:
            codigo = str(dados["codigo_acesso"])
            return codigo
        else:
            mensagem = f"({perito}) ⚠️ A resposta da API não contém um código válido."
            
            return None

    except Exception as e:
        mensagem = f"({perito}) ❌ Erro ao solicitar código de acesso na API: {e}"
        
        return None


def codigo_acesso(driver, codigo_acesso):
    time.sleep(6)
    mensagem = "🔎 Localizando o campo codigo de acesso... Por favor, aguarde."
    print(f'- (mensagem): {mensagem}')
    time.sleep(3)

    try:
        wait = WebDriverWait(driver, 15)
        campo = wait.until(EC.element_to_be_clickable((By.ID, "otp")))
        campo.clear()
        campo.send_keys(codigo_acesso)

        mensagem = f"✅ Codigo de acesso {codigo_acesso} inserido com sucesso!"
        print(f'- (mensagem): {mensagem}')
        return True

    except Exception as e:
        time.sleep(3)
        mensagem = f"❌ Erro ao tentar preencher o codigo de acesso: {e}. Entre em contato com a equipe de TI."
        
        return None


def clicar_validar_codigo(driver):
    time.sleep(3)
    mensagem = "Clicando no botão validar codigo de acesso, por favor, aguarde."
    print(f"{mensagem}")
    
    time.sleep(3)
    try:
        wait = WebDriverWait(driver, 15)
        xpath = "//input[@id='kc-login']"
        botao = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        botao.click()
        mensagem = "✅ botão validar clicado com sucesso! Vamos continuar com o protocolo 🚀"
        print(f"[OK] {mensagem}")
        return True
    except Exception:
        mensagem = "❌ Erro ao clicar no botão de validar acesso. Entre em contato com a equipe de TI."
        print(f'- (MSG): {mensagem}')
        return None


# Função Genérica
def interagir_com_elemento(
        driver,
        by,
        locator,
        acao="texto",  # "texto", "click" ou "exists"
        timeout=10,
        tentativas=3,
        mensagem_ws=True
):
    """
    Função genérica para interagir com elementos no Selenium.

    Recursos:
    - Tenta localizar o elemento várias vezes (tentativas configuráveis).
    - Pode extrair texto, clicar ou apenas verificar se existe.
    - Envia mensagens ao websocket via send_data_ws (opcional).
    - Retorna:
        - string (texto extraído)
        - True (se clicou)
        - False (se não encontrou e esgotou tentativas)
    """

    for tentativa in range(1, tentativas + 1):
        try:
            if mensagem_ws:
                send_data_ws(f"🔎 Tentando localizar elemento ({tentativa}/{tentativas})...")

            wait = WebDriverWait(driver, timeout)
            elemento = wait.until(EC.presence_of_element_located((by, locator)))

            # Se a ação for apenas verificar existência
            if acao == "exists":
                if mensagem_ws:
                    send_data_ws("🟢 Elemento encontrado!")
                return True

            # Se a ação for clicar
            elif acao == "click":
                elemento = wait.until(EC.element_to_be_clickable((by, locator)))
                elemento.click()

                if mensagem_ws:
                    send_data_ws("🟢 Clique realizado com sucesso!")
                return True

            # Se a ação for texto
            elif acao == "texto":
                texto = elemento.text.strip()

                if mensagem_ws:
                    send_data_ws(f"🟢 Texto extraído: {texto}")
                return texto

            else:
                raise ValueError("Ação inválida. Use: 'texto', 'click' ou 'exists'.")

        except Exception as e:
            if mensagem_ws:
                send_data_ws(f"⚠️ Falha ao interagir com elemento. Tentando novamente... (Erro: {e})")

            time.sleep(2)  # pequena espera antes de tentar de novo
            continue

    # Se chegou aqui, falhou todas as tentativas
    if mensagem_ws:
        send_data_ws("❌ Não foi possível interagir com o elemento após todas as tentativas.")

    return False


def detectar_perfil_usuario(driver):
    """
    Determina o perfil real do usuário no PJe.
    Caso existam múltiplos elementos .papel-usuario, utiliza SEMPRE o último.
    """

    xpath_papel = "//span[contains(@class, 'papel-usuario')]"

    try:
        # aguarda múltiplos elementos
        elementos = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, xpath_papel))
        )
    except Exception:
        send_data_ws("❌ Não foi possível localizar nenhum elemento .papel-usuario.")
        return None

    if not elementos:
        send_data_ws("❌ Nenhum elemento de papel encontrado.")
        return None

    # ✔ Pega SEMPRE o ÚLTIMO (perfil real)
    papel = elementos[-1].text.strip()
    papel_normalizado = papel.lower()

    send_data_ws(f"🔎 Papel encontrado: {papel}")

    # 🎯 Identifica perfil específico
    if "perito" in papel_normalizado:
        send_data_ws("🟢 Perfil identificado: PERITO")
        return "Perito"

    if "advogado" in papel_normalizado:
        send_data_ws("🟢 Perfil identificado: ADVOGADO")
        return "Advogado"

    # caso seja Jus Postulandi, Assistente, etc.
    send_data_ws(f"⚠️ Perfil genérico identificado: {papel}")
    return papel


def trocar_para_perfil_perito(driver, perfil="Perito"):
    time.sleep(5)
    try:

        # Checar Peril
        resultado  = detectar_perfil_usuario(driver)
        print(f'- (Perfil PJe): {resultado}')
        print(f'- (Perfil Perito): {perfil}')

        wait = WebDriverWait(driver, 15)

        if perfil != resultado:

            mensagem = "🔄 Trocando de perfil... Procurando a opção para alternar o modo de acesso."
            print(mensagem)
            

            botao_trocar = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[@aria-label='Trocar Órgão Julgador ou Perfil']")
            ))
            botao_trocar.click()

            time.sleep(5)

            mensagem = "🧑‍⚖️ Selecionando o perfil Perito... Aguarde um momento."
            print(mensagem)
            

            botao_perito = wait.until(EC.element_to_be_clickable(
                (By.XPATH, f"//button[contains(@aria-label, '{perfil}')]")
            ))
            botao_perito.click()

        mensagem = fr"✅ Perfil {perfil} ativado com sucesso! Pronto para seguir com o processo 🔧"
        print(mensagem)
        

        return True

    except Exception as e:
        mensagem = "❌ Erro ao tentar trocar para o perfil Perito. Entre em contato com a equipe de TI."
        print(f"[ERRO] {mensagem} - Detalhes: {e}")
        
        return None





def verificar_intimacoes(driver):
    mensagem = "🔍 Verificando se há novas intimações no painel do PJe..."
    print(mensagem)
    

    time.sleep(3)
    try:
        wait = WebDriverWait(driver, 15)
        painel_intimacoes = wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[@aria-label="Intimações"]')
        ))

        contador = painel_intimacoes.find_element(By.CLASS_NAME, "contador-principal").text

        mensagem = f"📬 Intimações encontradas: {contador}"
        print(mensagem)
        

        return contador

    except Exception as erro:
        mensagem = "❌ Erro ao tentar verificar novas intimações. Entre em contato com a equipe de TI."
        print(f"{mensagem} - Detalhes: {erro}")
        
        return None


def verificar_card_contador(driver, nome_card):
    """
    Lê o contador de qualquer card do painel do PJe, desde que o card tenha aria-label.

    Exemplo de 'nome_card':
        - "Intimações"
        - "Pendentes de Manifestação"
        - "Designações"
        - "Citações"
        - etc.

    Retorno:
        - string com o número do contador
        - "0" se vazio
        - None se erro
    """

    send_data_ws(f"🔍 Verificando o card: {nome_card}...")

    # 1) XPath do card baseado no aria-label
    xpath_card = f'//*[@aria-label="{nome_card}"]'

    # Verifica se o card existe
    card_existe = interagir_com_elemento(
        driver,
        By.XPATH,
        xpath_card,
        acao="exists",
        timeout=15,
        tentativas=3
    )

    if not card_existe:
        send_data_ws(f"❌ Não foi possível localizar o card '{nome_card}'.")
        return None

    # 2) XPath do contador dentro do card
    xpath_contador = f'{xpath_card}//div[contains(@class, "contador-principal")]'

    contador = interagir_com_elemento(
        driver,
        By.XPATH,
        xpath_contador,
        acao="texto",
        timeout=10,
        tentativas=3
    )

    if not contador:
        send_data_ws(f"⚠️ Card '{nome_card}' localizado, mas sem contador visível.")
        return "0"

    contador_normalizado = contador.strip()

    send_data_ws(f"📬 {nome_card}: {contador_normalizado}")

    return contador_normalizado


def clicar_intimacoes(driver):
    mensagem = "🖱️ Clicando em Intimações..."
    print(mensagem)
    

    time.sleep(3)
    try:
        wait = WebDriverWait(driver, 15)

        painel_intimacoes = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//*[@aria-label="Intimações"]'))
        )

        painel_intimacoes.click()

        mensagem = "✅ Clique em Intimações realizado com sucesso."
        print(mensagem)
        

        return True

    except Exception as erro:
        mensagem = f"❌ Erro ao clicar em Intimações: {erro}"
        print(mensagem)
        send_data_ws("❌ Erro ao clicar em novas intimações. Entre em contato com a equipe de TI.")
        return None


# v2
def clicar_card(driver, nome_card="Intimações"):
    """
    Clica em qualquer card do painel do PJe usando o aria-label.

    Exemplos de 'nome_card':
        - "Intimações"
        - "Pendentes de Manifestação"
        - "Designações"
        - "Citações"
        - "Audiências Pendentes"
        - etc.

    Retorna:
        - True → clique realizado
        - False / None → erro
    """

    send_data_ws(f"🖱️ Clicando no card: {nome_card} ...")

    # XPath baseado no aria-label do card
    xpath_card = f'//*[@aria-label="{nome_card}"]'

    # Usamos a função genérica para clicar
    resultado = interagir_com_elemento(
        driver,
        By.XPATH,
        xpath_card,
        acao="click",
        timeout=15,
        tentativas=3
    )

    if resultado:
        send_data_ws(f"✅ Clique no card '{nome_card}' realizado com sucesso.")
        return True

    send_data_ws(f"❌ Erro ao clicar no card '{nome_card}'. Entre em contato com o TI.")
    return None


def clicar_tomar_ciencia(driver):
    print('🖱️ Clicando em Tomar Ciência...')
    time.sleep(3)
    try:
        wait = WebDriverWait(driver, 15)

        botao_tomar_ciencia = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//*[@aria-label="Tomar ciência da intimação"]'))
        )

        botao_tomar_ciencia.click()

        print('✅ Clique em Tomar Ciência realizado com sucesso.')
        return True

    except Exception as erro:
        print('❌ Erro ao clicar em Tomar Ciência:', erro)
        mensagem = "❌ Erro ao clicar em Tomar Ciência. Entre em contato com a equipe de TI."
        print(mensagem)
        return None


def clicar_meu_painel(driver):
    print('🖱️ Clicando em MEu painel...')
    time.sleep(3)
    try:
        wait = WebDriverWait(driver, 15)

        botao_tomar_ciencia = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//*[@aria-label="Meu Painel"]'))
        )

        botao_tomar_ciencia.click()

        print('✅ Clique em Meu painel realizado com sucesso.')
        return True

    except Exception as erro:
        print('❌ Erro ao clicar em meu painel:', erro)
        return None


def _perfil_atual(driver):
    """Lê o perfil ativo (último span .papel-usuario do cabeçalho)."""
    spans = driver.find_elements(By.XPATH, "//span[contains(@class,'papel-usuario')]")
    return spans[-1].text.strip() if spans else ""


def garantir_perfil(driver, perfil_desejado, timeout=25, tentativas=2):
    """
    Garante que o perfil ativo no PJe KZ seja `perfil_desejado` (ex.: 'Advogado').

    O item do menu é um button.mat-menu-item cujo aria-label termina em
    " - Advogado", ex.:
        aria-label="ANA PAULA ... (000.000.000-00) - Advogado"
    e cujo texto visível é exatamente "Advogado". Casamos por aria-label
    (estável) OU texto exato, e usamos a presença desse botão clicável como a
    própria espera do carregamento assíncrono do overlay.

    Correção: a versão anterior exigia normalize-space()='Advogado', que nunca
    casava porque o item traz o nome completo do usuário antes do perfil.
    """
    wait = WebDriverWait(driver, timeout)
    alvo_lower = perfil_desejado.lower()

    atual = _perfil_atual(driver)
    print(f"[PERFIL] Atual: {atual!r} | Desejado: {perfil_desejado!r}")
    if alvo_lower in atual.lower():
        print("[PERFIL] Já está no perfil correto.")
        return True

    # Botão que abre o menu de perfis
    xpath_btn_menu = (
        "//button[contains(@class,'perfil-button') or "
        "@aria-label='Trocar Órgão Julgador ou Perfil']"
    )
    # Item do perfil desejado (aria-label contém '- Advogado' OU texto exato)
    xpath_item = (
        f"//button[contains(@class,'mat-menu-item') and ("
        f"contains(@aria-label, '- {perfil_desejado}') or "
        f"normalize-space(.)='{perfil_desejado}')]"
    )

    for tentativa in range(1, tentativas + 1):
        try:
            print(f"[PERFIL] Abrindo menu (tentativa {tentativa}/{tentativas})...")
            wait.until(EC.element_to_be_clickable((By.XPATH, xpath_btn_menu))).click()

            # Espera o ITEM real aparecer e ficar clicável (cobre o carregamento
            # assíncrono do overlay sem depender de qual cdk-overlay-pane é).
            alvo = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_item)))

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", alvo)
            try:
                alvo.click()
            except Exception:
                # TRT5 / Angular Material: clique normal às vezes falha → JS resolve
                driver.execute_script("arguments[0].click();", alvo)
            print(f"[PERFIL] Item '{perfil_desejado}' clicado.")

            # Confirma a troca lendo o cabeçalho (fonte da verdade)
            wait.until(lambda d: alvo_lower in _perfil_atual(d).lower())
            time.sleep(1.5)  # Angular settle
            print("[PERFIL] Perfil alterado com sucesso.")
            return True

        except Exception as e:
            print(f"[PERFIL][ERRO] Tentativa {tentativa} falhou: {e}")
            try:  # fecha overlay (ESC) e tenta de novo
                driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                time.sleep(0.5)
            except Exception:
                pass

    print(f"[PERFIL][ERRO] Não foi possível trocar para '{perfil_desejado}'.")
    return False


def garantir_perfil_v0(driver, perfil_desejado, timeout=10):
    """
    Garante que o perfil ativo seja o perfil_desejado.
    Ex.: 'Advogado', 'Perito'
    """

    try:
        # 🔎 Detecta perfil atual
        perfil_atual_el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.XPATH, "//span[contains(@class,'papel-usuario')]")
            )
        )
        perfil_atual = perfil_atual_el.text.strip()

        print(f"[PERFIL] Atual: {perfil_atual} | Desejado: {perfil_desejado}")

        # ✅ Já está no perfil correto
        if perfil_atual.lower() == perfil_desejado.lower():
            print("[PERFIL] Perfil correto, nenhuma ação necessária")
            return True

        # 🖱️ Abre menu de perfil
        btn_perfil = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(@class,'perfil-button')]")
            )
        )
        btn_perfil.click()

        # 🖱️ Clica no perfil desejado
        btn_perfil_destino = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//button[contains(@class,'mat-menu-item') and normalize-space()='{perfil_desejado}']"
                )
            )
        )
        btn_perfil_destino.click()

        print(f"[PERFIL] Alternando para perfil: {perfil_desejado}")

        # ⏳ Aguarda mudança REAL de contexto (URL OU perfil)
        WebDriverWait(driver, timeout).until(
            lambda d: perfil_desejado.lower() in d.page_source.lower()
                      or perfil_desejado.lower() in d.current_url.lower()
        )

        time.sleep(1.5)  # margem para AJAX / Angular estabilizar

        print("[PERFIL] Perfil alterado com sucesso")
        return True

    except Exception as e:
        print(f"[PERFIL][ERRO] Falha ao garantir perfil '{perfil_desejado}': {e}")
        return False


def _parse_date_or_none(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except Exception:
        return None


def _coletar_da_tabela(driver, perito_id=None):
    tbody = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, 'cdk-drop-list-0'))
    )

    linhas = tbody.find_elements(By.TAG_NAME, 'tr')
    qtd = len(linhas)

    mensagem = f'🔍 Lendo todas as linhas <tr> do tbody... ({qtd} linha(s))'
    print(mensagem)
    

    if not linhas:
        return [], 0

    lista_intimacoes = []
    vistos = set()  # 👈 controle de duplicados

    for index, linha in enumerate(linhas, start=1):
        tds = linha.find_elements(By.TAG_NAME, 'td')
        if len(tds) < 8:
            mensagem = f'⚠️ Linha {index} com colunas insuficientes. Ignorada.'
            print(mensagem)
            
            continue

        try:
            texto_coluna_2 = tds[1].text.strip().split("\n")
            tipo_e_numero = texto_coluna_2[0].split()
            tipo_acao = tipo_e_numero[0]
            numero_processo = tipo_e_numero[1]

            partes = numero_processo.split(".")
            trt_str = partes[3]
            trt = int(trt_str.lstrip("0"))

            span = tds[5].find_element(By.TAG_NAME, 'span')
            data_intimacao = span.text.strip()
            data_intimacao_raw = span.get_attribute("aria-label")

            prazo_final_ciencia = tds[6].text.strip()
            print(f"- (Prazo Final para Ciência): {prazo_final_ciencia}")

            # 👇 chave de unicidade no lote
            chave = (
                numero_processo,
                data_intimacao_raw,   # mesma data de intimação real
                trt,
                perito_id,
                "PERITO",
            )

            if chave in vistos:
                print(f"↪️ Duplicado no lote, ignorando: {chave}")
                continue

            vistos.add(chave)

            dados = {
                "numero_processo": numero_processo,
                "tipo_acao": tipo_acao,
                "prazo_entrega": tds[3].text.strip(),
                "data_designacao": tds[4].text.strip(),
                "data_intimacao": data_intimacao,
                "data_intimacao_real": data_intimacao_raw,
                "prazo_final_ciencia": prazo_final_ciencia or "",
                "situacao": tds[7].text.strip(),
                "tomar_ciencia": None,
                "trt": trt,
                "perito_id": perito_id,
                "parte_1": "",
                "parte_2": "",
                "orgao_julgador": "",
                "data_audiencia": "",
                "tem_prioridade": "",
                "tem_processo_associado": "",
                "perfil": "PERITO",
            }

            lista_intimacoes.append(dados)

        except Exception as erro_linha:
            mensagem = f'❌ Erro ao processar linha {index}: {erro_linha}'
            print(mensagem)
            
            continue

    return lista_intimacoes, len(lista_intimacoes)


def _coletar_da_tabela_v0(driver, perito_id=None):
    """
    Lê as linhas atuais da tabela (página já carregada)
    e retorna (lista_intimacoes, qtd_linhas_encontradas).
    """
    tbody = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, 'cdk-drop-list-0'))
    )

    linhas = tbody.find_elements(By.TAG_NAME, 'tr')
    qtd = len(linhas)

    mensagem = f'🔍 Lendo todas as linhas <tr> do tbody... ({qtd} linha(s))'
    print(mensagem)
    

    if not linhas:
        return [], 0

    lista_intimacoes = []

    for index, linha in enumerate(linhas, start=1):
        tds = linha.find_elements(By.TAG_NAME, 'td')
        if len(tds) < 8:
            mensagem = f'⚠️ Linha {index} com colunas insuficientes. Ignorada.'
            print(mensagem)
            
            continue

        try:
            texto_coluna_2 = tds[1].text.strip().split("\n")
            tipo_e_numero = texto_coluna_2[0].split()
            tipo_acao = tipo_e_numero[0]
            numero_processo = tipo_e_numero[1]

            partes = numero_processo.split(".")
            trt_str = partes[3]
            trt = int(trt_str.lstrip("0"))

            span = tds[5].find_element(By.TAG_NAME, 'span')
            data_intimacao = span.text.strip()
            data_intimacao_raw = span.get_attribute("aria-label")

            prazo_final_ciencia = tds[6].text.strip()
            print(f"- (Prazo Final para Ciência): {prazo_final_ciencia}")

            dados = {
                "numero_processo": numero_processo,
                "tipo_acao": tipo_acao,
                "prazo_entrega": tds[3].text.strip(),
                "data_designacao": tds[4].text.strip(),
                "data_intimacao": data_intimacao,
                "data_intimacao_real": data_intimacao_raw,
                "prazo_final_ciencia": prazo_final_ciencia or "",
                "situacao": tds[7].text.strip(),
                "tomar_ciencia": None,
                "trt": trt,
                "perito_id": perito_id,
                "parte_1": "",
                "parte_2": "",
                "orgao_julgador": "",
                "data_audiencia": "",
                "tem_prioridade": "",
                "tem_processo_associado": "",
                "perfil": "PERITO",
            }

            lista_intimacoes.append(dados)

        except Exception as erro_linha:
            mensagem = f'❌ Erro ao processar linha {index}: {erro_linha}'
            print(mensagem)
            
            continue

    return lista_intimacoes, qtd


def _salvar_e_enviar(lista_intimacoes, perito_id):
    registros_para_api = []     # o que será enviado para API/websocket
    novos_para_db = []          # apenas inserts
    novos_count = 0
    atualizados_count = 0

    # segurança extra: deduplicar também aqui, caso algo estranho passe
    vistos = set()

    for item in lista_intimacoes:
        try:
            chave = (
                item["numero_processo"],
                item["data_intimacao_real"],
                item["trt"],
                item["perito_id"],
                item.get("perfil", "PERITO"),
            )
            if chave in vistos:
                print(f"↪️ Duplicado em _salvar_e_enviar, ignorando: {chave}")
                continue
            vistos.add(chave)

            existe = Intimacoes.query.filter_by(
                numero_processo=item["numero_processo"],
                data_intimacao_real=item["data_intimacao_real"],
                trt=item["trt"],
                perito=item["perito_id"],
                perfil=item.get("perfil", "PERITO"),
            ).first()

            if existe:
                print(
                    f"⏭️ Registro existente no banco: "
                    f"{item['numero_processo']} ({item['data_intimacao_real']}) – UPDATE"
                )
                existe.tipo_acao = item["tipo_acao"]
                existe.prazo_entrega = _parse_date_or_none(item["prazo_entrega"])
                existe.data_designacao = _parse_date_or_none(item["data_designacao"])
                existe.data_intimacao = _parse_date_or_none(item["data_intimacao"])
                existe.data_intimacao_real = item["data_intimacao_real"]
                existe.prazo_final_ciencia = _parse_date_or_none(item["prazo_final_ciencia"])
                existe.situacao = item["situacao"]
                atualizados_count += 1
            else:
                nova = Intimacoes(
                    numero_processo=item["numero_processo"],
                    tipo_acao=item["tipo_acao"],
                    prazo_entrega=_parse_date_or_none(item["prazo_entrega"]),
                    data_designacao=_parse_date_or_none(item["data_designacao"]),
                    data_intimacao=_parse_date_or_none(item["data_intimacao"]),
                    data_intimacao_real=item["data_intimacao_real"],
                    prazo_final_ciencia=_parse_date_or_none(item["prazo_final_ciencia"]),
                    situacao=item["situacao"],
                    trt=item["trt"],
                    perito=item["perito_id"],
                    perfil=item.get("perfil", "PERITO"),
                )
                db.session.add(nova)
                novos_para_db.append(nova)
                novos_count += 1

            # entra na lista para API (apenas 1 vez por chave)
            # if not existe:  # só envia se realmente não existir NO POSTGRES
            registros_para_api.append(item)

        except Exception as e:
            print(f"⚠️ Erro ao adicionar ao banco: {e}")
            continue

    if registros_para_api:
        db.session.commit()
        total_lote = len(registros_para_api)
        mensagem = (
            f'📦 Lote processado: {total_lote} itens '
            f'({novos_count} novos, {atualizados_count} atualizados)'
        )
        print(mensagem)
        send_data_ws(mensagem, intimacoes=registros_para_api)
        send_intimacoes_api(registros_para_api, perito_id)
    else:
        print("ℹ️ Nenhuma intimação para processar (após deduplicação).")

    return registros_para_api


def _salvar_e_enviar_v1(lista_intimacoes, perito_id):
    novas_intimacoes = []

    for item in lista_intimacoes:
        try:
            existe = Intimacoes.query.filter_by(
                numero_processo=item["numero_processo"],
                data_intimacao_real=item["data_intimacao_real"],
                trt=item["trt"],
                perfil="PERITO"
            ).first()

            if existe:
                print(f"⏭️ Registro existente no banco: {item['numero_processo']} ({item['data_intimacao_real']}). Um evendo de update seja enviado para a API.")
                existe.tipo_acao = item["tipo_acao"]
                existe.tipo_acao=item["tipo_acao"]
                existe.prazo_entrega=_parse_date_or_none(item["prazo_entrega"])
                existe.data_designacao=_parse_date_or_none(item["data_designacao"])
                existe.data_intimacao=_parse_date_or_none(item["data_intimacao"])
                existe.data_intimacao_real=item["data_intimacao_real"]
                existe.prazo_final_ciencia=item["prazo_final_ciencia"]
                existe.situacao=item["situacao"]
            else:
                nova = Intimacoes(
                    numero_processo=item["numero_processo"],
                    tipo_acao=item["tipo_acao"],
                    prazo_entrega=_parse_date_or_none(item["prazo_entrega"]),
                    data_designacao=_parse_date_or_none(item["data_designacao"]),
                    data_intimacao=_parse_date_or_none(item["data_intimacao"]),
                    data_intimacao_real=item["data_intimacao_real"],
                    prazo_final_ciencia=None,
                    situacao=item["situacao"],
                    trt=item["trt"],
                    perito=item["perito_id"]
                )
                db.session.add(nova)

            novas_intimacoes.append(item)

        except Exception as e:
            print(f"⚠️ Erro ao adicionar ao banco: {e}")
            continue

    if novas_intimacoes:
        db.session.commit()
        mensagem = f'📦 Total de intimações novas salvas: {len(novas_intimacoes)}'
        print(mensagem)
        send_data_ws(mensagem, intimacoes=novas_intimacoes)
        send_intimacoes_api(novas_intimacoes, perito_id)
    else:
        print("ℹ️ Nenhuma nova intimação encontrada.")

    return novas_intimacoes


def _salvar_e_enviar_v0(lista_intimacoes, perito_id):
    novas_intimacoes = []

    for item in lista_intimacoes:
        try:
            existe = Intimacoes.query.filter_by(
                numero_processo=item["numero_processo"],
                data_intimacao_real=item["data_intimacao_real"],
                trt=item["trt"],
                perfil="PERITO"
            ).first()

            if existe:
                print(f"⏭️ Já existe no banco: {item['numero_processo']} ({item['data_intimacao_real']})")
                continue  # pula, não salva nem envia

            # Cria objeto novo
            nova = Intimacoes(
                numero_processo=item["numero_processo"],
                tipo_acao=item["tipo_acao"],
                prazo_entrega=_parse_date_or_none(item["prazo_entrega"]),
                data_designacao=_parse_date_or_none(item["data_designacao"]),
                data_intimacao=_parse_date_or_none(item["data_intimacao"]),
                data_intimacao_real=item["data_intimacao_real"],
                prazo_final_ciencia=None,
                situacao=item["situacao"],
                trt=item["trt"],
                perito=item["perito_id"]
            )
            db.session.add(nova)
            novas_intimacoes.append(item)

        except Exception as e:
            print(f"⚠️ Erro ao adicionar ao banco: {e}")
            continue

    if novas_intimacoes:
        db.session.commit()
        mensagem = f'📦 Total de intimações novas salvas: {len(novas_intimacoes)}'
        print(mensagem)
        send_data_ws(mensagem, intimacoes=novas_intimacoes)
        send_intimacoes_api(novas_intimacoes, perito_id)
    else:
        print("ℹ️ Nenhuma nova intimação encontrada.")

    return novas_intimacoes


def _ir_para_proxima_pagina(driver, ancora_primeira_linha_text):
    """
    Clica na seta 'próxima página' e aguarda a tabela atualizar
    (primeira linha muda de texto ou DOM fica stale).
    Retorna True se conseguiu ir; False caso contrário.
    """
    try:
        botao_proximo = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "span.mat-button-wrapper i.fa-chevron-right"))
        )
    except Exception as e:
        print(f"⚠️ Botão de próxima página não encontrado: {e}")
        send_data_ws(f"⚠️ Botão de próxima página não encontrado: {e}")
        return False

    # Tenta capturar a primeira linha atual para usar como âncora
    try:
        tbody = driver.find_element(By.ID, 'cdk-drop-list-0')
        linhas_atuais = tbody.find_elements(By.TAG_NAME, 'tr')
        primeira_linha_element = linhas_atuais[0] if linhas_atuais else None
    except Exception:
        primeira_linha_element = None

    botao_proximo.click()

    # Aguarda mudança: o elemento fica stale OU o texto da primeira linha muda
    try:
        if primeira_linha_element:
            WebDriverWait(driver, 10).until(EC.staleness_of(primeira_linha_element))
        # Garante presença do tbody novamente
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, 'cdk-drop-list-0'))
        )
        # Pequeno respiro
        time.sleep(0.5)

        # Confirma que mudou o conteúdo (se houver âncora de texto)
        if ancora_primeira_linha_text:
            tentativas = 0
            while tentativas < 10:
                tbody_novo = driver.find_element(By.ID, 'cdk-drop-list-0')
                linhas_novas = tbody_novo.find_elements(By.TAG_NAME, 'tr')
                if linhas_novas:
                    texto_atual = linhas_novas[0].text.strip()
                    if texto_atual != ancora_primeira_linha_text:
                        break
                time.sleep(0.3)
                tentativas += 1
    except Exception as e:
        print(f"⚠️ Falha ao aguardar atualização da próxima página: {e}")
        send_data_ws(f"⚠️ Falha ao aguardar atualização da próxima página: {e}")
        return False

    return True


def get_intimacoes_dict_list(driver, perito_id):
    try:
        # ========== PÁGINA 1 ==========
        lista_p1, qtd_p1 = _coletar_da_tabela(driver, perito_id)

        version_old = False
        if version_old:
            novas_p1 = _salvar_e_enviar_v0(lista_p1, perito_id)
        else:
            novas_p1 = _salvar_e_enviar(lista_p1, perito_id)

        # Se menos de 10 linhas, não há próxima página
        if qtd_p1 < 10:
            return novas_p1

        # Guarda âncora (texto da 1ª linha) para confirmar refresh
        ancora_text = ""
        try:
            tbody = driver.find_element(By.ID, 'cdk-drop-list-0')
            linhas = tbody.find_elements(By.TAG_NAME, 'tr')
            if linhas:
                ancora_text = linhas[0].text.strip()
        except Exception:
            pass

        # ========== IR PARA PÁGINA 2 ==========
        if not _ir_para_proxima_pagina(driver, ancora_text):
            return novas_p1  # não conseguiu avançar

        # ========== PÁGINA 2 ==========
        lista_p2, qtd_p2 = _coletar_da_tabela(driver, perito_id)
        novas_p2 = _salvar_e_enviar(lista_p2, perito_id)

        # Retorna tudo (p1 + p2)
        return (novas_p1 or []) + (novas_p2 or [])

    except Exception as erro:
        mensagem = f'❌ Erro ao montar lista de intimações: {erro}'
        print(mensagem)
        
        return None


def alterar_trt(driver, trt):
    try:
        print(f'🌐 Alterando URL para TRT-{trt}')
        time.sleep(2)
        driver.get(f"https://pje.trt{trt}.jus.br/primeirograu/login.seam")
        return driver
    except Exception as e:
        print(f'❌ Erro ao alterar URL para TRT-{trt}: {e}')
        return None


def _extrair_valor_apos_quebra(texto: str):
    """
    Extrai o valor real de células no formato:
    'Rótulo ABC\nvalor'
    Sempre retorna somente a parte após o último '\n'.
    """

    if not texto:
        return ""

    partes = [p.strip() for p in texto.split("\n") if p.strip()]

    # Sempre pega o último valor
    return partes[-1] if partes else ""


def _separar_partes_advogado(partes_texto: str):
    """
    Extrai parte_1 e parte_2 de um texto no formato:
        'NOME1 x NOME2'
        'NOME1\nx\nNOME2'
        'NOME1    x    NOME2'
    Retorna parte_1, parte_2 devidamente limpos.
    """

    if not partes_texto:
        return "", ""

    # Remove quebras de linha duplicadas e espaços exagerados
    texto_limpo = re.sub(r"\s+", " ", partes_texto).strip()

    # Agora garantimos que existe ' x ' como separador
    # Versão robusta: captura o "x" isolado
    padrao = r"\bx\b"  # x sozinho, não dentro de palavras

    if re.search(padrao, texto_limpo, flags=re.IGNORECASE):
        partes = re.split(padrao, texto_limpo, flags=re.IGNORECASE)
        if len(partes) == 2:
            parte_1 = partes[0].strip()
            parte_2 = partes[1].strip()
            return parte_1, parte_2

    # Caso não tenha "x", devolve tudo como parte_1
    return texto_limpo, ""


def coletar_tabela_advogado(driver, perito_id=None):
    tbody = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "tbody.cdk-drop-list"))
    )
    linhas = tbody.find_elements(By.TAG_NAME, "tr")
    total = len(linhas)

    resultados = []
    vistos = set()  # 👈 controle de duplicados

    for idx in range(total):
        try:
            linhas = tbody.find_elements(By.TAG_NAME, "tr")
            linha = linhas[idx]

            tds = linha.find_elements(By.TAG_NAME, "td")
            if len(tds) < 10:
                send_data_ws(f"⚠️ Linha {idx} ignorada: colunas insuficientes.")
                continue

            col_proc = tds[1].text.strip().split("\n")
            tipo_e_num = col_proc[1].split()
            tipo_acao = tipo_e_num[0]
            numero_processo = tipo_e_num[-1]
            trt = int(numero_processo.split(".")[-2])

            partes_raw = col_proc[-1].strip()
            parte_1, parte_2 = _separar_partes_advogado(partes_raw)

            orgao_julgador = _extrair_valor_apos_quebra(tds[4].text.strip())
            data_criacao = _extrair_valor_apos_quebra(tds[5].text.strip())
            data_audiencia = _extrair_valor_apos_quebra(tds[6].text.strip())
            data_audiencia = data_audiencia if data_audiencia != "-" else ""
            data_ciencia = _extrair_valor_apos_quebra(tds[7].text.strip())
            data_ciencia = data_ciencia if data_ciencia != "-" else ""
            prazo_final = _extrair_valor_apos_quebra(tds[8].text.strip())
            prazo_final = prazo_final if prazo_final != "-" else ""

            prioridade = False
            associado = False

            try:
                tds[3].find_element(By.CSS_SELECTOR, "i.fa-exclamation-triangle")
                prioridade = True
            except:
                pass

            try:
                tds[3].find_element(By.CSS_SELECTOR, "i.fa-link")
                associado = True
            except:
                pass

            # 👇 chave de unicidade no lote (note uso de data_criacao)
            chave = (
                numero_processo,
                data_criacao,
                trt,
                perito_id,
                "ADVOGADO",
            )

            if chave in vistos:
                print(f"↪️ Duplicado no lote (ADV): {chave}")
                continue

            vistos.add(chave)

            dados = {
                "numero_processo": numero_processo,
                "tipo_acao": tipo_acao,
                "parte_1": parte_1,
                "parte_2": parte_2,
                "orgao_julgador": orgao_julgador,
                "data_intimacao": data_criacao,
                "data_intimacao_real": "",  # se depois você tiver a "real" em aria-label, encaixa aqui
                "data_audiencia": data_audiencia,
                "data_tomar_ciencia": data_ciencia,
                "prazo_final_ciencia": prazo_final,
                "tem_prioridade": prioridade,
                "tem_processo_associado": associado,
                "perito_id": perito_id,
                "trt": trt,
                "situacao": "Pendentes de Manifestação",
                "prazo_entrega": "",
                "data_designacao": "",
                "tomar_ciencia": None,
                "perfil": "ADVOGADO",
            }

            resultados.append(dados)

        except Exception as erro:
            print(f'- (except): {erro}')
            send_data_ws(f"❌ Erro ao processar linha {idx}: {erro}")
            continue

    print(f'- (Lista de dados)000: {resultados}')
    return resultados


def coletar_tabela_advogado_v0(driver, perito_id=None):
    """
    Lê a tabela completa do perfil ADVOGADO e extrai uma lista de dicionários.
    """

    tbody = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "tbody.cdk-drop-list"))
    )
    linhas = tbody.find_elements(By.TAG_NAME, "tr")
    total = len(linhas)


    resultados = []

    for idx in range(total):
        try:

            # RECAPTURA A LINHA – evita stale element
            linhas = tbody.find_elements(By.TAG_NAME, "tr")
            linha = linhas[idx]

            tds = linha.find_elements(By.TAG_NAME, "td")
            if len(tds) < 10:
                send_data_ws(f"⚠️ Linha {idx} ignorada: colunas insuficientes.")
                continue

            # ========== COLUNA 1: PROCESSO + PARTES ==========
            col_proc = tds[1].text.strip().split("\n")

            # Exemplo: ['CSAC 0001136-54.2024.5.06.0016', 'ALCINEIDE ... x CORREIOS']
            tipo_e_num = col_proc[1].split()
            tipo_acao = tipo_e_num[0]
            numero_processo = tipo_e_num[-1]
            trt = int(numero_processo.split(".")[-2])

            partes_raw = col_proc[-1].strip()
            parte_1, parte_2 = _separar_partes_advogado(partes_raw)

            # ========== COLUNA 4: ÓRGÃO JULGADOR ==========
            orgao_julgador = _extrair_valor_apos_quebra(tds[4].text.strip())

            # ========== COLUNA 5: DATA DE CRIAÇÃO ==========
            data_criacao = _extrair_valor_apos_quebra(tds[5].text.strip())

            # ========== COLUNA 6: DATA AUDIÊNCIA ==========
            data_audiencia = _extrair_valor_apos_quebra(tds[6].text.strip())
            data_audiencia = data_audiencia if data_audiencia != "-" else ""

            # ========== COLUNA 7: DATA CIÊNCIA ==========
            data_ciencia = _extrair_valor_apos_quebra(tds[7].text.strip())
            data_ciencia = data_ciencia if data_ciencia != "-" else ""

            # ========== COLUNA 8: PRAZO FINAL ==========
            prazo_final = _extrair_valor_apos_quebra(tds[8].text.strip())
            prazo_final = prazo_final if prazo_final != "-" else ""

            # ========== COLUNA 3 e 4: ÍCONES (prioridade, associado) ==========
            prioridade = False
            associado = False

            # prioridade: existe ícone fa-exclamation-triangle
            try:
                tds[3].find_element(By.CSS_SELECTOR, "i.fa-exclamation-triangle")
                prioridade = True
            except:
                pass

            # processo associado: existe ícone fa-link
            try:
                tds[3].find_element(By.CSS_SELECTOR, "i.fa-link")
                associado = True
            except:
                pass

            # ========== MONTANDO OBJETO FINAL ==========
            dados = {
                "numero_processo": numero_processo,
                "tipo_acao": tipo_acao,
                "parte_1": parte_1,
                "parte_2": parte_2,
                "orgao_julgador": orgao_julgador,
                "data_intimacao": data_criacao,
                "data_intimacao_real": "", # Data em texto detalhado
                "data_audiencia": data_audiencia,
                "data_tomar_ciencia": data_ciencia,
                "prazo_final_ciencia": prazo_final,
                "tem_prioridade": prioridade,
                "tem_processo_associado": associado,
                "perito_id": perito_id,
                "trt": trt,
                "situacao": "Pendentes de Manifestação",
                "prazo_entrega": "",
                "data_designacao": "",

                "tomar_ciencia": None,
                "perfil": "ADVOGADO",
            }

            resultados.append(dados)

        except Exception as erro:
            print(f'- (except): {erro}')
            send_data_ws(f"❌ Erro ao processar linha {idx}: {erro}")
            continue

    print(f'- (Lista de dados)000: {resultados}')
    return resultados


def salvar_e_enviar_advogado(lista_intimacoes, perito_id):
    registros_para_api = []     # o que será enviado para API/websocket
    novos_para_db = []          # apenas inserts
    novos_count = 0
    atualizados_count = 0

    # segurança extra: deduplicar também aqui, caso algo estranho passe
    vistos = set()

    for item in lista_intimacoes:
        try:
            chave = (
                item["numero_processo"],
                item["data_intimacao_real"],
                item["trt"],
                item["perito_id"],
                item.get("perfil", "PERITO"),
            )
            if chave in vistos:
                print(f"↪️ Duplicado em _salvar_e_enviar, ignorando: {chave}")
                continue
            vistos.add(chave)

            existe = Intimacoes.query.filter_by(
                numero_processo=item["numero_processo"],
                data_intimacao=item["data_intimacao"],
                trt=item["trt"],
                perito=item["perito_id"],
                perfil=item.get("perfil", "PERITO"),
            ).first()

            if existe:
                print(
                    f"⏭️ Registro existente no banco: "
                    f"{item['numero_processo']} ({item['data_intimacao_real']}) – UPDATE"
                )
                existe.tipo_acao = item["tipo_acao"]
                existe.prazo_entrega = _parse_date_or_none(item["prazo_entrega"])
                existe.data_designacao = _parse_date_or_none(item["data_designacao"])
                existe.data_intimacao = _parse_date_or_none(item["data_intimacao"])
                existe.data_intimacao_real = item["data_intimacao_real"]
                existe.prazo_final_ciencia = item["prazo_final_ciencia"]
                existe.situacao = item["situacao"]
                atualizados_count += 1
            else:
                nova = Intimacoes(
                    numero_processo=item["numero_processo"],
                    tipo_acao=item["tipo_acao"],
                    prazo_entrega=_parse_date_or_none(item["prazo_entrega"]),
                    data_designacao=_parse_date_or_none(item["data_designacao"]),
                    data_intimacao=_parse_date_or_none(item["data_intimacao"]),
                    data_intimacao_real=item["data_intimacao_real"] if item["data_intimacao_real"] else item["data_intimacao"],
                    prazo_final_ciencia=_parse_date_or_none(item["prazo_final_ciencia"]),
                    situacao=item["situacao"],
                    trt=item["trt"],
                    perito=item["perito_id"],
                    perfil=item.get("perfil", "PERITO"),
                )
                db.session.add(nova)
                novos_para_db.append(nova)
                novos_count += 1

            # entra na lista para API (apenas 1 vez por chave)
            if not existe:  # só envia se realmente não existir NO POSTGRES
                registros_para_api.append(item)

        except Exception as e:
            print(f"⚠️ Erro ao adicionar ao banco: {e}")
            continue

    if registros_para_api:
        db.session.commit()
        total_lote = len(registros_para_api)
        mensagem = (
            f'📦 Lote processado: {total_lote} itens '
            f'({novos_count} novos, {atualizados_count} atualizados)'
        )
        print(mensagem)
        send_data_ws(mensagem, intimacoes=registros_para_api)
        send_intimacoes_api(registros_para_api, perito_id)
    else:
        print("ℹ️ Nenhuma intimação para processar (após deduplicação).")

    return registros_para_api


def salvar_e_enviar_advogado_v0(lista_processos, perito_id=None):
    novas = []

    print(f'- (Lista de Processos): {lista_processos}')

    for proc in lista_processos:
        try:
            exists = Intimacoes.query.filter_by(
                numero_processo=proc["numero_processo"],
                data_intimacao=proc["data_intimacao"],
                trt=proc["trt"],
                perfil="ADVOGADO"
            ).first()

            if exists:
                exists.tipo_acao = proc["tipo_acao"]
                exists.parte_1 = proc["parte_1"]
                exists.parte_2 = proc["parte_2"]
                exists.orgao_julgador = proc["orgao_julgador"]
                exists.data_intimacao = _parse_date_or_none(proc["data_intimacao"])
                exists.data_audiencia = _parse_date_or_none(proc["data_audiencia"])
                exists.data_tomar_ciencia = _parse_date_or_none(proc["data_tomar_ciencia"])
                exists.prazo_final_ciencia = _parse_date_or_none(proc["prazo_final_ciencia"])
                exists.prioridade_processual = proc["tem_prioridade"]
                exists.processo_associado = proc["tem_processo_associado"]

                # STATUS TOMAR CIÊNCIA
                exists.tomar_ciencia = bool(proc["data_tomar_ciencia"])
            else:
                novo = Intimacoes(
                    numero_processo=proc["numero_processo"],
                    tipo_acao=proc["tipo_acao"],
                    parte_1=proc["parte_1"],
                    parte_2=proc["parte_2"],
                    orgao_julgador=proc["orgao_julgador"],
                    data_intimacao=_parse_date_or_none(proc["data_intimacao"]),
                    data_audiencia=_parse_date_or_none(proc["data_audiencia"]),
                    data_tomar_ciencia=_parse_date_or_none(proc["data_tomar_ciencia"]),
                    prazo_final_ciencia=_parse_date_or_none(proc["prazo_final_ciencia"]),
                    trt=proc["trt"],
                    perito=proc["perito_id"],
                    perfil="ADVOGADO",
                )
                db.session.add(novo)

            novas.append(proc)
        except Exception as e:
            send_data_ws(f"⚠️ Erro ao salvar processo {proc['numero_processo']}: {e}")
            continue

    if novas:
        db.session.commit()
        send_data_ws(f"( APP-ADV ) 📦 Total de {len(novas)} intimações novas salvas (ADVOGADO).")
        send_intimacoes_api(novas, perito_id)

    else:
        send_data_ws("ℹ️ Nenhum processo novo para salvar (perfil Advogado).")

    return novas


def get_processos_advogado(driver, perito_id):
    send_data_ws("📄 Extraindo tabela de processos (perfil Advogado)...")

    try:
        lista = coletar_tabela_advogado(driver, perito_id)
        print(f'- (Lista de dados): {lista}')
        novas = salvar_e_enviar_advogado(lista, perito_id)
        print(f'- (Novas): {novas}')
        return novas

    except Exception as erro:
        send_data_ws(f"❌ Erro ao coletar processos do advogado: {erro}")
        return None


def detectar_estado_pje(driver):
    """
    Detecta o estado real do PJe com base no DOM.
    """

    # ✅ Já autenticado
    if driver.find_elements(By.XPATH, '//*[@aria-label="Meu Painel"]'):
        return "AUTENTICADO"

    # 🔐 Tela de código (2FA)
    if driver.find_elements(By.ID, "otp"):
        return "CODIGO_ACESSO"

    # 🔑 Escolha do certificado digital
    if driver.find_elements(
        By.XPATH,
        "//a[.//span[contains(text(), 'Seu certificado digital')]]"
    ):
        return "CERTIFICADO"

    # 🔁 Botão inicial do PDPJ / SSO
    if driver.find_elements(By.ID, "btnSsoPdpj"):
        return "PDPJ"

    return "DESCONHECIDO"


def garantir_autenticacao(driver, perito, max_tentativas=5):
    tentativa = 0

    while tentativa < max_tentativas:
        tentativa += 1
        estado = detectar_estado_pje(driver)

        print(f"[AUTH] Estado detectado: {estado}")

        if estado == "AUTENTICADO":
            return True

        if estado == "PDPJ":
            clicar_botao_pdpj(driver)

        elif estado == "CERTIFICADO":
            clicar_certificado_digital(driver)
            preencher_senha_desktop(perito)

        elif estado == "CODIGO_ACESSO":
            codigo = gerar_codigo(perito)
            if not codigo:
                continue
            codigo_acesso(driver, codigo)
            clicar_validar_codigo(driver)

        else:
            time.sleep(1)

    return False
