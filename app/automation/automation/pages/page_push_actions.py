import time
import json
import os, re
from app.automation.Models.scripts_pje import *
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException
)

def detectar_contexto_push(driver):
    """
    Detecta se a página atual está pronta para o fluxo de push.
    """

    if driver.find_elements(By.XPATH, "//button[@id='btnCadastro']"):
        return "PUSH_OK"

    if driver.find_elements(By.XPATH, '//*[@aria-label="Meu Painel"]'):
        return "PAINEL"

    if driver.find_elements(By.ID, "btnSsoPdpj"):
        return "DESLOGADO"

    return "DESCONHECIDO"



# =========================================================
# SCRAPER – RESPONSÁVEL APENAS POR EXTRAÇÃO
# =========================================================

class ProcessosScraper:

    def __init__(self, driver, trt, chaves_unicas, data_execucao=None, timeout=20, page_atual=1):
        self.driver = driver
        self.trt = trt
        self.timeout = timeout
        self.wait = WebDriverWait(driver, timeout)
        self.data = []
        self.page = page_atual

        # 🔑 chaves compartilhadas entre TRTs do MESMO DIA
        self.chaves_unicas = chaves_unicas

        # 🔥 Data/hora da extração (uma por execução)
        self.data_extracao = data_execucao

    def carregar_existentes(self, path="processos_push.json"):

        try:
            if not os.path.exists(path):
                return

            with open(path, "r", encoding="utf-8") as f:
                dados = json.load(f)

            for item in dados:
                chave = f"{item['tribunal']}|{item['numero_processo']}"
                self.chaves_unicas.add(chave)
        except Exception as e:
            print(f'- (except)[carregar_existentes]: {e}')

    def wait_page_ready(self, timeout=10):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "tr.tr-class")
                )
            )
            return True
        except TimeoutException:
            return False

    def get_rows(self):
        return self.driver.find_elements(By.CSS_SELECTOR, "tr.tr-class")

    def parse_row(self, row, index):
        try:
            spans = row.find_elements(By.CSS_SELECTOR, "span.texto-preto")

            numero_processo = spans[0].text.strip()
            data_cadastro = spans[1].text.strip()

            # 🔍 Extrai apenas o número do processo (sem classe / tipo)
            match = re.search(
                r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}",
                numero_processo
            )

            if not match:
                return None

            numero_processo = match.group(0)

            # 🔑 chave única
            chave = f"TRT{self.trt}|{numero_processo}"

            # ⛔ ignora duplicado
            if chave in self.chaves_unicas:
                return None

            self.chaves_unicas.add(chave)

            print(f'- (Índice): {index} | - (Processo): {numero_processo} | - (Página): {self.page} | - (Data): {self.data_extracao}')

            return {
                "data_extracao": self.data_extracao,
                "tribunal": f"TRT{self.trt}",
                "pagina": self.page,
                "linha": index,
                "numero_processo": numero_processo,
                "data_cadastro": data_cadastro,
            }

        except (IndexError, StaleElementReferenceException):
            return None

    def scrape_page(self):
        rows = self.get_rows()

        for index, row in enumerate(rows, start=1):
            registro = self.parse_row(row, index)
            if registro:
                self.data.append(registro)

    def next_page(self):
        """
        Avança para a próxima página de forma segura.
        Retorna False APENAS quando já está na última página.
        """

        try:
            # 🔍 Localiza o botão SEM exigir clickability
            next_button = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[@aria-label='Próximo']")
                )
            )

            classes = next_button.get_attribute("class") or ""

            # 🚫 Última página
            if "mat-button-disabled" in classes or next_button.get_attribute("disabled"):
                print(f"[INFO] Última página alcançada: {self.page}")
                return False

            primeiro_atual = self._get_primeiro_processo()

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", next_button
            )

            try:
                next_button.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", next_button)

            self.page += 1

            self.wait_pagina_carregada()
            self.tabela_estavel()

            return True

        except TimeoutException:
            # fallback seguro → considera última página
            print(f"[WARN] Timeout ao tentar avançar. Página atual: {self.page}")
            return False

    def next_page_v1(self):
        """
        Avança para a próxima página de forma segura.
        Retorna False APENAS quando já está na última página.
        """

        try:
            # 🔍 Localiza o botão SEM exigir clickability
            next_button = self.wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//button[@aria-label='Próximo']")
                )
            )

            classes = next_button.get_attribute("class") or ""

            # 🚫 Última página
            if "mat-button-disabled" in classes or next_button.get_attribute("disabled"):
                print(f"[INFO] Última página alcançada: {self.page}")
                return False

            primeiro_atual = self._get_primeiro_processo()

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", next_button
            )

            try:
                next_button.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", next_button)

            self.page += 1

            # 🔄 Aguarda mudança real da tabela
            WebDriverWait(self.driver, 30).until(
                lambda d: self._get_primeiro_processo() != primeiro_atual
            )

            self.wait_page_ready()
            self.wait_pagina_carregada()
            return True

        except TimeoutException:
            # fallback seguro → considera última página
            print(f"[WARN] Timeout ao tentar avançar. Página atual: {self.page}")
            return False

    def next_page_v0(self):
        """
        Avança para a próxima página aguardando:
        1) clique
        2) ripple desaparecer
        3) primeiro registro mudar
        """
        try:
            primeiro_atual = self._get_primeiro_processo()

            next_button = self.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@aria-label='Próximo']")
                )
            )

            classes = next_button.get_attribute("class") or ""
            if "mat-button-disabled" in classes or "disabled" in classes:
                return False

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", next_button
            )

            next_button.click()
            self.page += 1

            # 🔥 1) Aguarda ripple sumir
            self.wait_ripple_disappear()

            # 🔥 2) Aguarda mudança REAL do conteúdo
            WebDriverWait(self.driver, 30).until(
                lambda d: self._get_primeiro_processo() != primeiro_atual
            )

            # 🔥 3) Aguarda estabilização mínima da tabela
            self.wait_page_ready()

            return True

        except TimeoutException:
            return False

    def scrape_all(self):
        """
        Percorre todas as páginas, garantindo extração da última página.
        """

        if not self.wait_page_ready():
            print(f"[INFO] TRT {self.trt}: nenhum registro encontrado.")
            return []

        while True:
            # 🔥 SEMPRE extrai a página atual
            self.scrape_page()

            # 🔚 Se não houver próxima, sai
            if not self.next_page():
                break

        return self.data

    def scrape_all_v0(self):
        """
        Percorre todas as páginas.
        Retorna lista vazia se não houver registros.
        """

        tem_registros = self.wait_page_ready()

        if not tem_registros:
            print(f"[INFO] TRT {self.trt}: nenhum registro encontrado.")
            return []

        while True:
            self.scrape_page()
            if not self.next_page():
                break

        return self.data

    def _get_range_text(self):
        try:
            span = self.driver.find_element(
                By.CSS_SELECTOR, "span.total-registros"
            )
            return span.text.strip()
        except Exception:
            return None

    def _get_primeiro_processo(self):
        try:
            row = self.driver.find_element(By.CSS_SELECTOR, "tr.tr-class")
            span = row.find_element(By.CSS_SELECTOR, "span.texto-preto")
            return span.text.strip()
        except Exception:
            return None

    def wait_ripple_disappear(self, timeout=15):
        """
        Aguarda o efeito ripple do Angular Material desaparecer,
        indicando que a ação de paginação terminou.
        """
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, "span.mat-button-ripple")
                )
            )
        except TimeoutException:
            # Se não existir ripple, segue o fluxo
            pass

    def wait_pagina_carregada_v0(self, timeout=30):
        wait = WebDriverWait(self.driver, timeout)

        try:
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "div.sr-only[aria-label='Notificação']"),
                    "Página carregada"
                )
            )
            time.sleep(0.7)

        except TimeoutException:
            raise Exception(
                "Timeout: a página não sinalizou 'Página carregada'."
            )

    def wait_pagina_carregada(self, timeout=40):
        wait = WebDriverWait(self.driver, timeout)

        try:
            # Aguarda o overlay aparecer (quando existe)
            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.cdk-overlay-backdrop")
                )
            )
        except TimeoutException:
            # Pode não aparecer em páginas rápidas → segue fluxo
            pass

        # Aguarda o overlay SUMIR (sinal real de carregamento concluído)
        wait.until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "div.cdk-overlay-backdrop")
            )
        )

        # Pequeno buffer para estabilização do DOM
        time.sleep(0.3)


    def tabela_estavel(self):
        WebDriverWait(self.driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
        )


    def wait_pagina_carregada_v1(self, timeout=30):
        wait = WebDriverWait(self.driver, timeout)

        try:
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "div.sr-only[aria-label='Notificação']"),
                    "Página carregada"
                )
            )
            time.sleep(0.7)

        except TimeoutException:
            raise Exception(
                "Timeout: a página não sinalizou 'Página carregada'."
            )

    def localizar_processo(self, numero_processo_alvo):
        """
        Percorre a tabela página a página até localizar o processo.
        Retorna dict com dados + WebElement da linha ou None.
        """

        print(f"[INFO] Buscando processo {numero_processo_alvo} na tabela...")

        # garante que a primeira página está pronta
        if not self.wait_page_ready():
            print("[WARN] Tabela não carregou.")
            return None

        while True:
            rows = self.get_rows()
            print(f"[DEBUG] Página {self.page} | Linhas: {len(rows)}")

            for index, row in enumerate(rows, start=1):
                try:
                    spans = row.find_elements(By.CSS_SELECTOR, "span.texto-preto")
                    if not spans:
                        continue

                    texto = spans[0].text.strip()

                    if numero_processo_alvo in texto:
                        print(
                            f"[OK] Processo encontrado | "
                            f"Página {self.page} | Linha {index}"
                        )

                        return {
                            "pagina": self.page,
                            "linha": index,
                            "row": row,
                            "numero_processo": numero_processo_alvo,
                        }

                except StaleElementReferenceException:
                    continue

            # não achou na página → tenta próxima
            if not self.next_page():
                print("[INFO] Processo não encontrado em nenhuma página.")
                return None

    def localizar_processo_na_pagina(self, numero_processo, tentativas=3):
        """
        Localiza o processo na página atual de forma segura contra StaleElement.
        Retorna WebElement da <tr> ou None.
        """

        for tentativa in range(1, tentativas + 1):
            try:
                rows = self.driver.find_elements(By.CSS_SELECTOR, "tr.tr-class")

                for idx in range(len(rows)):
                    try:
                        # 🔁 rebusca a linha SEMPRE
                        row = self.driver.find_elements(By.CSS_SELECTOR, "tr.tr-class")[idx]
                        texto = row.text

                        if numero_processo in texto:
                            print(f"[OK] Processo encontrado (tentativa {tentativa})")
                            return row

                    except StaleElementReferenceException:
                        # linha específica ficou inválida → tenta próxima
                        continue

                # percorreu todas as linhas sem achar
                return None

            except StaleElementReferenceException:
                print(f"[WARN] DOM alterado (tentativa {tentativa}), tentando novamente...")

        print("[ERRO] Não foi possível localizar o processo (stale persistente)")
        return None

    def obter_pagina_atual(self, timeout=10):
        wait = WebDriverWait(self.driver, timeout)
        try:
            el = wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "mat-select .mat-select-value-text")
                )
            )
            pagina = int(el.text.strip())
            self.page = pagina
            return pagina
        except Exception:
            return self.page or 1

    def ir_para_pagina_por_select(self, pagina_destino: int, timeout=15):
        wait = WebDriverWait(self.driver, timeout)

        select = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "mat-select"))
        )
        select.click()

        painel = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "mat-select-panel"))
        )

        opcoes = painel.find_elements(By.TAG_NAME, "mat-option")

        for opcao in opcoes:
            if opcao.text.strip() == str(pagina_destino):
                opcao.click()
                self.wait_pagina_carregada()
                self.page = pagina_destino
                return True

        raise Exception(f"Página {pagina_destino} não encontrada no select")

    def ir_para_pagina_inteligente(self, pagina_destino: int, total_tela: int = None,
                                   itens_por_pagina: int = 50, timeout: int = 20):
        """
        Navegação inteligente:
        - Se total_tela <= itens_por_pagina → só 1 página (não navega)
        - Diferença até 2 → usa botões Anterior/Próximo (com checagem de disabled)
        - Diferença maior → usa select (mat-select)
        """

        # normaliza
        try:
            pagina_destino = int(pagina_destino)
        except (TypeError, ValueError):
            raise Exception(f"Página inválida: {pagina_destino!r}")

        if pagina_destino < 1:
            pagina_destino = 1

        # total_tela pode vir de fora (você já tem), ou lemos aqui
        if total_tela is None:
            try:
                total_tela = self.obter_total_registros_tela()
            except Exception:
                total_tela = 0

        # ✅ se só existe 1 página, não tenta navegar
        if total_tela and total_tela <= itens_por_pagina:
            self.page = 1
            if pagina_destino != 1:
                print(
                    f"[INFO] total_tela={total_tela} <= {itens_por_pagina}: só 1 página. Ignorando destino={pagina_destino}.")
            return True

        # lê página atual do select (ou usa memória)
        pagina_atual = self.obter_pagina_atual()
        self.page = pagina_atual

        if pagina_atual == pagina_destino:
            return True

        diff = pagina_destino - pagina_atual

        # ✅ diferenças pequenas → botões (sem timeout bobo)
        if abs(diff) <= 2:
            label = "Próximo" if diff > 0 else "Anterior"
            passos = abs(diff)

            for _ in range(passos):
                ok = self.clicar_paginacao(label, timeout=timeout)
                if not ok:
                    # botão desabilitado → não dá pra ir além
                    print(
                        f"[WARN] Botão '{label}' desabilitado. Página atual={self.page}. Destino={pagina_destino}.")
                    return False

                # atualiza estado
                self.page = self.obter_pagina_atual()

            return self.page == pagina_destino

        # ✅ diferenças grandes → select
        try:
            ok = self.ir_para_pagina_por_select(pagina_destino, timeout=timeout)
            self.page = pagina_destino
            return ok
        except TimeoutException:
            print(f"[ERRO] Timeout indo para página {pagina_destino} via select.")
            return False
        except Exception as e:
            print(f"[ERRO] Falha indo para página {pagina_destino} via select: {e}")
            return False

    def ir_para_pagina_inteligente_v0(self, pagina_destino: int, timeout=20):
        pagina_destino = int(pagina_destino)
        pagina_atual = self.obter_pagina_atual()

        print(f"[INFO] Página atual: {pagina_atual} | Destino: {pagina_destino}")

        if pagina_atual == pagina_destino:
            return True

        diff = pagina_destino - pagina_atual

        # 🔹 Pequena diferença → botões
        if abs(diff) <= 2:
            botao_label = "Próximo" if diff > 0 else "Anterior"
            passos = abs(diff)

            for _ in range(passos):
                botao = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, f"//button[@aria-label='{botao_label}']")
                    )
                )
                botao.click()
                self.wait_pagina_carregada()

            self.page = pagina_destino
            return True

        # 🔹 Diferença grande → select
        return self.ir_para_pagina_por_select(pagina_destino, timeout)

    def clicar_excluir_da_linha(self, row):
        try:
            btn = row.find_element(
                By.XPATH,
                ".//button[@aria-label='Excluir processo']"
            )
            btn.click()
            return True
        except StaleElementReferenceException:
            return False
        except Exception as e:
            print(f"[ERRO] Falha ao clicar em excluir: {e}")
            return False

    def localizar_processo_com_fallback(self, numero_processo):
        pagina_original = self.obter_pagina_atual()

        # 1️⃣ página atual
        row = self.localizar_processo_na_pagina(numero_processo)
        if row:
            return row

        # 2️⃣ próxima página
        if self.clicar_paginacao("Próximo"):
            row = self.localizar_processo_na_pagina(numero_processo)
            if row:
                return row

        # 3️⃣ volta para página original
        self.ir_para_pagina_inteligente(pagina_original)

        # 4️⃣ página anterior
        if self.clicar_paginacao("Anterior"):
            row = self.localizar_processo_na_pagina(numero_processo)
            if row:
                return row

        # 5️⃣ volta para original
        self.ir_para_pagina_inteligente(pagina_original)

        return None

    def localizar_processo_com_fallback_v0(self, numero_processo: str):
        paginas_testar = [
            self.page,
            self.page + 1,
            self.page - 1,
        ]

        for pagina in paginas_testar:
            if pagina <= 0:
                continue

            print(f"[INFO] Tentando localizar processo na página {pagina}")
            self.ir_para_pagina_inteligente(pagina)

            rows = self.driver.find_elements(By.CSS_SELECTOR, "tr.tr-class")
            for row in rows:
                if numero_processo in row.text:
                    print(f"[OK] Processo encontrado na página {pagina}")
                    return row

        print(f"[WARN] Processo {numero_processo} não encontrado após fallback")
        return None

    def obter_total_registros_tela(self, timeout=10):
        """
        Extrai o total de registros exibido na tela.
        Exemplo do texto: '1 - 50 de 3896'
        Retorna int (3896) ou 0 se não existir.
        """
        try:
            span = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "span.total-registros")
                )
            )

            texto = span.text.strip()

            # Extrai o número após 'de'
            match = re.search(r"de\s+(\d+)", texto)
            return int(match.group(1)) if match else 0

        except TimeoutException:
            # Não existe total-registros → sem dados
            return 0

    def _is_disabled(self, el):
        """Detecta disabled (atributo HTML) e classes do Angular Material."""
        try:
            if el.get_attribute("disabled"):
                return True
            classes = (el.get_attribute("class") or "").lower()
            if "mat-button-disabled" in classes or "disabled" in classes:
                return True
        except Exception:
            pass
        return False

    def clicar_paginacao(self, label: str, timeout=10):
        """
        Clica em 'Próximo' ou 'Anterior' se estiver habilitado.
        Retorna False se estiver desabilitado.
        """
        wait = WebDriverWait(self.driver, timeout)
        btn = wait.until(
            EC.presence_of_element_located((By.XPATH, f"//button[@aria-label='{label}']"))
        )

        if self._is_disabled(btn):
            return False

        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, f"//button[@aria-label='{label}']")))
            btn.click()
        except Exception:
            # fallback JS
            self.driver.execute_script("arguments[0].click();", btn)

        self.wait_pagina_carregada()
        return True

    def save_json(self, path="processos_extraidos.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)


# =========================================================
# AUTOMAÇÃO DE NAVEGAÇÃO (CLIQUE + CONTROLE DE LOAD)
# =========================================================

class AutomacaoPush:

    def __init__(self, driver, trt=None, pagina_atual=1):
        self.driver = driver
        self.trt = trt  # 🔥 guarda o tribunal atual
        self.trt_atual = None
        self.first_execution = True
        self.pagina_atual = pagina_atual

        self.BTN_MEU_PAINEL = (
            By.XPATH,
            "//button[@aria-label='Meu Painel']"
        )

        self.BTN_MENU_COMPLETO = (By.ID, "botao-menu")

        self.BTN_CADASTRO = (
            By.XPATH,
            "//div[contains(@class,'item-center') and normalize-space()='Cadastro']"
        )

        self.BTN_PUSH = (
            By.XPATH,
            "//div[contains(@class,'item-center') and normalize-space()='PUSH']"
        )

        self.BTN_ADDPUSH = (
            By.XPATH,
            "//button[@aria-label='Adicionar Processos para Acompanhamento']"
        )

        self.INPUT_NUMERO_PROCESSO = (
            By.ID,
            "inputNumeroProcesso"
        )

        self.BTN_INCLUIR = (
            By.XPATH,
            "//button[@aria-label='Incluir']"
        )

        self.BTN_FECHAR_MODAL = (
            By.XPATH,
            "//a[contains(@class,'btn-fechar-link')]"
        )

        self.BTN_PUSH_MENU = (
            By.XPATH,
            "//button[@aria-label='Push']"
        )

    # -----------------------------------------------------

    def garantir_trt(self, trt_destino: str, grau="primeirograu"):

        if self.trt_atual == trt_destino:
            print(f"[INFO] TRT {trt_destino} já ativo. Mantendo página.")
            return 'pje-atual'

        print(f"[INFO] Mudando para TRT {trt_destino}")

        url = f"https://pje.trt{trt_destino}.jus.br/{grau}/login.seam"
        self.driver.get(url)

        self.trt_atual = trt_destino

    # -----------------------------------------------------

    def wait_pagina_carregada(self, timeout=30):
        wait = WebDriverWait(self.driver, timeout)

        try:
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.CSS_SELECTOR, "div.sr-only[aria-label='Notificação']"),
                    "Página carregada"
                )
            )
            time.sleep(0.7)

        except TimeoutException:
            raise Exception(
                "Timeout: a página não sinalizou 'Página carregada'."
            )

    # -----------------------------------------------------

    def safe_click(self, locator, timeout=15):
        wait = WebDriverWait(self.driver, timeout)

        try:
            element = wait.until(EC.element_to_be_clickable(locator))
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", element
            )
            element.click()
            return True

        except TimeoutException:
            print(f"[SAFE_CLICK] Elemento não encontrado: {locator}")
            return False

    # -----------------------------------------------------

    def aumentar_itens_por_pagina(self, timeout=20):
        """
        Abre o mat-select de itens por página e seleciona o ÚLTIMO valor disponível
        (maior quantidade).
        """
        wait = WebDriverWait(self.driver, timeout)

        # 1️⃣ Localiza TODOS os mat-select habilitados
        mat_selects = wait.until(
            EC.presence_of_all_elements_located(
                (
                    By.XPATH,
                    "//mat-select[@role='combobox' and not(@aria-disabled='true')]"
                )
            )
        )

        if len(mat_selects) < 2:
            raise Exception(
                f"Esperado pelo menos 2 mat-select, encontrados {len(mat_selects)}."
            )

        # 2️⃣ Seleciona o SEGUNDO mat-select
        mat_select = mat_selects[1]

        # Scroll até o mat-select
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", mat_select
        )
        time.sleep(0.7)

        # Clique para abrir o select
        try:
            mat_select.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", mat_select)

        # 2️⃣ Aguarda o painel de opções (overlay do Angular Material)
        panel = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.mat-select-panel")
            )
        )

        # 3️⃣ Captura todas as opções disponíveis
        options = panel.find_elements(By.CSS_SELECTOR, "mat-option")

        if not options:
            raise Exception("Nenhuma opção encontrada no seletor de itens por página.")

        # 4️⃣ Seleciona o ÚLTIMO item (maior valor)
        last_option = options[-1]

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", last_option
        )
        time.sleep(0.7)

        try:
            last_option.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", last_option)

        # 5️⃣ Aguarda o Angular recarregar a tabela
        self.wait_pagina_carregada()


    def ir_para_pagina_json(self, pagina_destino: int, timeout=20):
        """
        Navega até a página indicada pelo JSON usando os botões de paginação.
        Assume que os itens por página já foram ajustados (ex: 50).
        """

        # 🔒 NORMALIZAÇÃO FORTE
        try:
            pagina_destino = int(pagina_destino)
        except (TypeError, ValueError):
            raise Exception(
                f"Página inválida recebida do JSON: {pagina_destino!r}"
            )

        if pagina_destino <= 1:
            print("[INFO] Página destino é 1. Nenhuma navegação necessária.")
            return True

        wait = WebDriverWait(self.driver, timeout)

        def pagina_atual():
            """
            Obtém o número da página atual no paginator.
            Ex: 'Página 3 de 12' ou '3 / 12'
            """
            try:
                el = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.mat-paginator-range-label")
                    )
                )
                texto = el.text
                # exemplos possíveis: "101 – 150 de 432" → página = 3 se 50 por página
                numeros = re.findall(r"\d+", texto)
                if len(numeros) >= 2:
                    inicio = int(numeros[0])
                    return ((inicio - 1) // 50) + 1
            except Exception:
                pass
            return 1  # fallback seguro

        pagina_atual_num = pagina_atual()
        print(f"[INFO] Página atual detectada: {pagina_atual_num}")

        if pagina_atual_num > pagina_destino:
            print(
                f"[WARN] Página atual ({pagina_atual_num}) é maior que a destino ({pagina_destino}). "
                "Recomenda-se recarregar a tela antes."
            )
            return False

        while pagina_atual_num < pagina_destino:
            try:
                botao_proximo = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[@aria-label='Próximo']")
                    )
                )

                # se estiver desabilitado, não há mais páginas
                classes = botao_proximo.get_attribute("class") or ""
                if "mat-button-disabled" in classes or "disabled" in classes:
                    print("[WARN] Botão Próximo desabilitado antes de alcançar a página destino.")
                    return False

                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", botao_proximo
                )
                time.sleep(0.3)

                try:
                    botao_proximo.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", botao_proximo)

                # aguarda a tabela recarregar
                self.wait_pagina_carregada()
                time.sleep(0.4)

                pagina_atual_num += 1
                print(f"[INFO] Avançou para página {pagina_atual_num}")

            except Exception as e:
                print(f"[ERRO] Falha ao navegar para página {pagina_destino}: {e}")
                return False

        print(f"[OK] Página {pagina_destino} alcançada com sucesso.")
        return True

    # -----------------------------------------------------

    def escrever_campo(self, locator, texto, limpar=True, tab_apos=True, verbose=False, timeout=10):
        """
        Escreve em um campo input de forma robusta (Angular Material friendly).

        Params:
          locator: tupla (By.X, "valor")
          texto: str
          limpar: bool
          tab_apos: bool -> envia TAB no final (ajuda a disparar validação/blur do Angular)
          verbose: bool
          timeout: int
        """
        try:
            wait = WebDriverWait(self.driver, timeout)

            el = wait.until(EC.element_to_be_clickable(locator))

            # garante que está visível
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.15)

            # foca
            el.click()
            time.sleep(0.05)

            if limpar:
                # limpeza robusta (clear + ctrl+a/backspace)
                try:
                    el.clear()
                except Exception:
                    pass

                try:
                    el.send_keys(Keys.CONTROL, "a")
                    el.send_keys(Keys.BACKSPACE)
                except Exception:
                    # fallback JS
                    self.driver.execute_script("arguments[0].value='';", el)

                time.sleep(0.05)

            # escreve
            el.send_keys(str(texto))

            # dispara blur/validação do Angular
            if tab_apos:
                el.send_keys(Keys.TAB)

            if verbose:
                print(f"✔ Escreveu '{texto}' no campo {locator}")

            return True

        except Exception as e:
            if verbose:
                print(f"❌ Falha ao escrever no campo {locator}: {e}")

            # fallback final via JS (quando send_keys falha)
            try:
                el = self.driver.find_element(*locator)
                self.driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input')); arguments[0].dispatchEvent(new Event('change'));",
                    el,
                    str(texto)
                )
                if tab_apos:
                    el.send_keys(Keys.TAB)
                return True
            except Exception:
                return None

    # -----------------------------------------------------





    def capturar_mensagem_feedback(self, timeout=5, verbose=True):
        """
        Captura mensagens de feedback (snackbar / toast / alert)
        Blindada contra StaleElementReferenceException.
        """

        seletores = [
            # Angular Material Snackbar
            (By.CSS_SELECTOR, "snack-bar-container"),
            (By.CSS_SELECTOR, ".mat-snack-bar-container"),

            # Genérico
            (By.CSS_SELECTOR, "[role='alert']"),
            (By.CSS_SELECTOR, "[aria-live='assertive']"),
            (By.CSS_SELECTOR, "[aria-live='polite']"),
        ]

        fim = time.time() + timeout

        while time.time() < fim:
            for by, selector in seletores:
                try:
                    elemento = WebDriverWait(self.driver, 1).until(
                        EC.presence_of_element_located((by, selector))
                    )

                    # 🔁 Tenta ler o texto com retry curto
                    try:
                        texto = elemento.text.strip()
                    except StaleElementReferenceException:
                        # re-localiza imediatamente
                        elemento = self.driver.find_element(by, selector)
                        texto = elemento.text.strip()

                    if texto:
                        if verbose:
                            print(f"📢 Feedback capturado: {texto}")

                        return {
                            "sucesso": True,
                            "mensagem": texto
                        }

                except TimeoutException:
                    continue
                except StaleElementReferenceException:
                    continue

            time.sleep(0.2)  # pequeno respiro

        if verbose:
            print("ℹ️ Nenhuma mensagem de feedback detectada.")

        return {
            "sucesso": False,
            "mensagem": None
        }


    def capturar_feedback_ou_validar_total(self, total_anterior=None, timeout=5, verbose=True):
        """
        1) Tenta capturar snackbar
        2) Se não conseguir, compara total da página
        """

        # 🔎 1 - Tenta capturar mensagem normalmente
        resultado = self.capturar_mensagem_feedback(timeout=timeout, verbose=verbose)

        if resultado["sucesso"]:
            return resultado

        # 🔁 2 - Fallback: verificar se total aumentou
        if total_anterior is not None:

            total_atual = self.obter_total_registros_tela(timeout=5)

            if total_atual is not None and total_atual > total_anterior:
                if verbose:
                    print(f"✅ Total aumentou: {total_anterior} → {total_atual}")

                return {
                    "sucesso": True,
                    "mensagem": f"Registro inserido (validação por total: {total_atual})"
                }

            else:
                if verbose:
                    print(f"❌ Total não aumentou ({total_anterior} → {total_atual})")

        return {
            "sucesso": False,
            "mensagem": "Não foi possível confirmar inserção"
        }



    def capturar_mensagem_feedback_v0(
            self,
            timeout=5,
            verbose=True
    ):
        """
        Captura mensagens de feedback (snackbar / toast / alert)
        Funciona para Angular Material, React, Vue, etc.
        """

        seletores = [
            # Angular Material Snackbar
            (By.CSS_SELECTOR, "snack-bar-container"),
            (By.CSS_SELECTOR, ".mat-snack-bar-container"),

            # Genérico
            (By.CSS_SELECTOR, "[role='alert']"),
            (By.CSS_SELECTOR, "[aria-live='assertive']"),
            (By.CSS_SELECTOR, "[aria-live='polite']"),
        ]

        for by, selector in seletores:
            try:
                elemento = WebDriverWait(self.driver, timeout).until(
                    EC.visibility_of_element_located((by, selector))
                )

                texto = elemento.text.strip()

                if texto:
                    if verbose:
                        print(f"📢 Feedback capturado: {texto}")

                    return {
                        "sucesso": True,
                        "mensagem": texto
                    }

            except TimeoutException:
                continue

        if verbose:
            print("ℹ️ Nenhuma mensagem de feedback detectada.")

        return {
            "sucesso": False,
            "mensagem": None
        }


    # -----------------------------------------------------

    def close_modal(self, timeout=10):
        try:
            wait = WebDriverWait(self.driver, timeout)

            botao_fechar = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@class,'btn-fechar-link')]")
                )
            )

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                botao_fechar
            )
            time.sleep(0.2)

            try:
                botao_fechar.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", botao_fechar)

            print("❎ Modal fechado com sucesso.")

            # Aguarda o modal SUMIR do DOM
            wait.until(
                EC.invisibility_of_element_located(
                    (By.TAG_NAME, "pje-push-cadastro")
                )
            )

            return True

        except Exception as e:
            print(f"❌ Falha ao fechar modal: {e}")
            return False

    # -----------------------------------------------------

    def obter_total_registros_tela(self, timeout=10):
        """
        Extrai o total de registros exibido na tela.
        Exemplo do texto: '1 - 50 de 3896'
        Retorna int (3896) ou 0 se não existir.
        """
        try:
            span = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "span.total-registros")
                )
            )

            texto = span.text.strip()

            # Extrai o número após 'de'
            match = re.search(r"de\s+(\d+)", texto)
            return int(match.group(1)) if match else 0

        except TimeoutException:
            # Não existe total-registros → sem dados
            return 0

    # -----------------------------------------------------

    def function_main_push(self, chaves_unicas, data_execucao):

        contexto = detectar_contexto_push(self.driver)
        print(f"[CTX] Contexto detectado: {contexto}")

        if contexto != "PUSH_OK":
            print("[CTX] Reabrindo painel corretamente...")
            clicar_meu_painel(self.driver)
            self.wait_pagina_carregada()


        # MEU PAINAL -> Tratar avisos
        self.safe_click(self.BTN_MEU_PAINEL, 5)

        get_except = False
        try:
            # MENU COMPLETO
            self.safe_click(self.BTN_MENU_COMPLETO, 5)
        except Exception as e:
            print(f'- (Elemento não localizado)[BTN_MENU_COMPLETO]: {e}')
            get_except = True

            # MENU PUSH
            self.safe_click(self.BTN_PUSH_MENU, 5)

        if get_except is False:

            # CADASTRO
            status_btnCad =  self.safe_click(self.BTN_CADASTRO)
            print(f'- (Status): {status_btnCad}')

            # PUSH
            self.safe_click(self.BTN_PUSH, 5)


        # 🔥 AUMENTA ITENS POR PÁGINA
        self.aumentar_itens_por_pagina()


        # ⏳ Aguarda página carregar novamente
        self.wait_pagina_carregada()

        # 🔢 Total informado pela tela
        total_tela = self.obter_total_registros_tela()

        # =================================================
        # 🔥 EXTRAÇÃO DE DADOS APÓS ENTRAR EM PUSH
        # =================================================
        print("[INFO] Iniciando extração dos dados da tabela PUSH...")

        scraper = ProcessosScraper(
            self.driver,
            self.trt,
            chaves_unicas=chaves_unicas,
            data_execucao=data_execucao
        )
        dados = scraper.scrape_all()

        print(
            f"[OK] TRT {self.trt} | "
            f"Extraídos: {len(dados)} | "
            f"Total tela: {total_tela}"
        )

        return dados, total_tela


    def function_main_cad_push(self, numero_processo, context):

        get_except = False
        result = None

        # MENU COMPLETO
        # if not context == 'pje-atual':
        # MEU PAINAL -> Tratar avisos
        self.safe_click(self.BTN_MEU_PAINEL, 5)

        try:
            # MENU COMPLETO
            result = self.safe_click(self.BTN_MENU_COMPLETO, 5)
            print(f'- (Resuldado): {result}')
            get_except = True if result is False else False
        except Exception as e:
            print(f'- (Elemento não localizado)[BTN_MENU_COMPLETO]: {e}')
            get_except = True

        if get_except or result is False:
            # MENU PUSH
            self.safe_click(self.BTN_PUSH_MENU, 5)

        if get_except is False:

            # CADASTRO
            # self.safe_click(self.BTN_CADASTRO, 5)
            if not self.safe_click(self.BTN_CADASTRO):
                raise RuntimeError("Contexto inválido para BTN_CADASTRO")

            # PUSH
            self.safe_click(self.BTN_PUSH, 5)

        # Pegar total de registros antes
        total_antes = self.obter_total_registros_tela(5)

        # BTN ADICIONAR
        self.safe_click(
            self.BTN_ADDPUSH, 5
        )

        self.escrever_campo(
            self.INPUT_NUMERO_PROCESSO,
            numero_processo,
            limpar=True,
            verbose=True
        )

        self.safe_click(
            self.BTN_INCLUIR, 5
        )

        # ⏳ Aguarda página carregar novamente
        self.wait_pagina_carregada()

        # 🔄 Recarrega a página
        # self.driver.refresh()
        self.close_modal()

        # ⏳ Aguarda página carregar novamente
        self.wait_pagina_carregada()

        msg_return = self.capturar_feedback_ou_validar_total(
            total_anterior=total_antes
        )
        # msg = self.capturar_mensagem_feedback(5)
        # print(f'- (Msg): {msg}')
        # scraper.save_json("processos_push.json")
        print(f"[OK] Processo {numero_processo} processado. | [Msg]: {msg_return}")

        return msg_return


    def function_main_del_push(self, pagina, numero_processo, context):

        get_except = False

        # MENU COMPLETO
        if not context == 'pje-atual':

            # MEU PAINAL -> Tratar avisos
            self.safe_click(self.BTN_MEU_PAINEL, 5)

            try:
                # MENU COMPLETO
                self.safe_click(self.BTN_MENU_COMPLETO, 5)
            except Exception as e:
                print(f'- (Elemento não localizado)[BTN_MENU_COMPLETO]: {e}')
                get_except = True

                # MENU PUSH
                self.safe_click(self.BTN_PUSH_MENU, 5)


            if get_except is False:

                # CADASTRO
                # self.safe_click(self.BTN_CADASTRO, 5)
                if not self.safe_click(self.BTN_CADASTRO):
                    raise RuntimeError("Contexto inválido para BTN_CADASTRO")

                # PUSH
                self.safe_click(self.BTN_PUSH, 5)


        # 🔥 AUMENTA ITENS POR PÁGINA
        self.aumentar_itens_por_pagina()

        # ⏳ Aguarda página carregar novamente
        self.wait_pagina_carregada()

        # 🔢 Total informado pela tela
        total_tela = self.obter_total_registros_tela()
        print(f'- (Qtd. Itens): {total_tela}')

        # self.ir_para_pagina_json(pagina, 10)

        # =================================================
        # 🔥 EXTRAÇÃO DE DADOS APÓS ENTRAR EM PUSH
        # =================================================
        print("[INFO] Iniciando extração dos dados da tabela PUSH...")

        scraper = ProcessosScraper(
            self.driver,
            self.trt,
            chaves_unicas=set(),
            data_execucao=None,
            timeout=20,
            page_atual=self.pagina_atual,
        )

        pagina_destino = int(pagina) if str(pagina).strip().isdigit() else 1
        ok = scraper.ir_para_pagina_inteligente(pagina_destino, total_tela=total_tela, itens_por_pagina=50, timeout=20)
        if not ok:
            print(f"[WARN] Não foi possível navegar até a página {pagina_destino}.")

        # resultado = scraper.localizar_processo(numero_processo)
        row = scraper.localizar_processo_com_fallback(numero_processo)
        if not row:
            return {
                "resultado": "NAO_ENCONTRADO",
                "mensagem": "Processo não localizado após reordenação"
            }

        if not scraper.clicar_excluir_da_linha(row):
            return {"sucesso": False, "mensagem": "Falha ao clicar em excluir"}

        msg = self.capturar_mensagem_feedback(5)
        print(f'- (Msg): {msg}')

        return msg
