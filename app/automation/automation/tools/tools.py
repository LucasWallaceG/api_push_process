import os
import re
import time
import msvcrt
import contextlib
from typing import Set, List, Dict

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

from pywinauto import Desktop
from pywinauto.keyboard import send_keys


class Tools:
    # ---------------- CONFIG ----------------
    PIN = "Jrs#2909"  # PIN padrão (hardcode)
    PIN_ENV_VAR = "TOKEN_PIN"  # variável de ambiente (tem prioridade)
    PIN_LOCK_PATH = r"C:\Temp\__pin_lock__.lck"
    PIN_DIALOG_RE = r"(Informe a senha|PIN|Segurança do Windows|Windows Security)"

    # ----------------------------------------

    def __init__(self, driver, timeout=30):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    def click(self, locator):
        try:
            el = self.wait.until(EC.element_to_be_clickable(locator))
            el.click()
            return True
        except Exception as e:
            print(e)
            return None

    def clicar_se_possivel(self, locator):
        try:
            el = self.wait.until(EC.element_to_be_clickable(locator))
            el.click()
            print(f"INFO: Elemento {locator} foi clicado com sucesso.")
            return True
        except TimeoutException:
            print(f"AVISO: Elemento {locator} não estava clicável. O clique foi ignorado.")
            return False

    def gerar_codigo(self):
        time.sleep(3)
        url = "http://192.168.11.38:5010/gerador/acesso"

        payload = {
            "token": "jrs-access",
            "perito": "paula"
        }

        mensagem = "Solicitando codigo de acesso na api"
        print(mensagem)
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
                mensagem = "⚠️ A resposta da API não contém um código válido."
                print(mensagem)
                return None

        except Exception as e:
            mensagem = f"❌ Erro ao solicitar código de acesso na API: {e}"
            print(mensagem)
            return None

    def clicar_validar_codigo(self, driver):
        time.sleep(3)
        mensagem = "Clicando no botão validar codigo de acesso, por favor, aguarde."
        print(mensagem)
        time.sleep(3)
        try:
            wait = WebDriverWait(driver, 15)
            xpath = "//input[@id='kc-login']"
            botao = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            botao.click()

            mensagem = "✅ botão validar clicado com sucesso! Vamos continuar com o protocolo 🚀"
            print(f"[OK] {mensagem}")
            return True
        except Exception as e:
            mensagem = "❌ Erro ao clicar no botão de validar acesso. Entre em contato com a equipe de TI."
            print(f"[ERRO] {mensagem}", e)
            return None

    @staticmethod
    def _extrai_cnj(texto: str) -> str | None:
        """Extrai o número de processo no formato CNJ de uma string."""
        m = re.search(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", texto or "")
        return m.group(0) if m else None

    def pagina_atual(self, locator, verbose=False):
        try:
            elemento = self.wait.until(EC.presence_of_element_located(locator))
            texto = elemento.text.strip()
            if verbose:
                print(f"📄 Página atual detectada: {texto}")
            return texto
        except Exception as e:
            if verbose:
                print(f"⚠ Falha ao obter paginação atual: {e}")
            return None

    def listar_tbody(self, locator, alvo: str, verbose: bool = False) -> Dict[str, List[str]]:

        time.sleep(3)

        alvo_cnj = self._extrai_cnj(alvo) or (alvo.strip() if alvo else "")
        if verbose:
            print("--- Iniciando extração do tbody (versão alvo único) ---")
            print(f"Alvo recebido: {alvo!r} | Alvo normalizado: {alvo_cnj!r}")

        tbody = self.wait.until(EC.presence_of_element_located(locator))
        linhas = tbody.find_elements(By.TAG_NAME, "tr")

        marcados: List[str] = []
        visiveis: List[str] = []

        for idx, linha in enumerate(linhas, start=1):
            celulas = linha.find_elements(By.TAG_NAME, "td")
            if len(celulas) < 3:
                continue

            texto_completo = celulas[2].text.strip()
            numero_processo = self._extrai_cnj(texto_completo)

            if numero_processo:
                visiveis.append(numero_processo)

            if verbose:
                print(f"Linha {idx}: '{numero_processo}'")

            # Se bateu com o alvo, tenta marcar
            if numero_processo and (numero_processo == alvo_cnj):
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", linha)

                    try:
                        alvo_click = celulas[0].find_element(By.CSS_SELECTOR, "label.mat-checkbox-layout")
                    except Exception:
                        alvo_click = celulas[0].find_element(By.CSS_SELECTOR, ".mat-checkbox-inner-container")

                    try:
                        alvo_click.click()
                        time.sleep(0.2)
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", alvo_click)

                    checked = False
                    try:
                        mat_cb = celulas[0].find_element(By.CSS_SELECTOR, "mat-checkbox, .mat-checkbox")
                        try:
                            inp = mat_cb.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                            checked = (inp.get_attribute("aria-checked") == "true")
                        except Exception:
                            checked = "mat-checkbox-checked" in mat_cb.get_attribute("class")
                    except Exception:
                        checked = False

                    if checked:
                        marcados.append(numero_processo)
                        if verbose:
                            print(f"✔ Checkbox marcado para {numero_processo}")
                    else:
                        if verbose:
                            print(f"✖ Não marcou (linha {idx} / {numero_processo})")

                except Exception as e:
                    if verbose:
                        print(f"⚠ Falha ao clicar no checkbox da linha {idx}: {e}")

                break

        if verbose:
            print("--- Extração finalizada ---")

        return {"marcados": marcados, "visiveis": visiveis}

    def listar_processos(self, locator, processos=None, verbose=False):
        """
        Percorre todo o tbody e coleta os números de processo.
        Retorna a lista (processos) com todos os CNJs encontrados.
        """
        time.sleep(3)

        if processos is None:
            processos = []  # inicia uma lista nova se não foi passada

        if verbose:
            print("--- Iniciando extração do tbody (somente leitura) ---")

        tbody = self.wait.until(EC.presence_of_element_located(locator))
        linhas = tbody.find_elements(By.TAG_NAME, "tr")

        for idx, linha in enumerate(linhas, start=1):
            celulas = linha.find_elements(By.TAG_NAME, "td")
            if len(celulas) >= 3:
                texto_completo = celulas[2].text.strip()
                numero_processo = self._extrai_cnj(texto_completo)

                if numero_processo:
                    processos.append(numero_processo)
                    if verbose:
                        print(f"Linha {idx}: {numero_processo}")

        if verbose:
            print("--- Extração finalizada ---")
            print(f"Total coletado: {len(processos)} processos")

        return processos

    def escrever_campo(self, locator, texto, limpar=True, verbose=False):
        try:
            campo = self.wait.until(EC.element_to_be_clickable(locator))

            if limpar:
                campo.clear()

            campo.send_keys(texto)

            if verbose:
                print(f"✔ Escreveu '{texto}' no campo {locator}")
            return True

        except Exception as e:
            if verbose:
                print(f"❌ Falha ao escrever no campo {locator}: {e}")
            return None

    def _get_pin(self) -> str:
        """
        Retorna o PIN.
        - Se TOKEN_PIN estiver definida no ambiente, usa ela.
        - Senão, usa o PIN fixo definido na classe.
        """
        return os.getenv(self.PIN_ENV_VAR, self.PIN)

    @contextlib.contextmanager
    def pin_lock(self):
        """
        Lock simples de 1 byte em arquivo para evitar
        que dois processos tentem digitar PIN ao mesmo tempo.
        """
        os.makedirs(os.path.dirname(self.PIN_LOCK_PATH), exist_ok=True)
        with open(self.PIN_LOCK_PATH, "a+b") as fh:
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass

    def esperar_dialogo_pin(self, timeout=30):
        """
        Espera aparecer uma janela de PIN/Segurança do Windows.
        Retorna o handle da janela (pywinauto) ou None.
        """
        end = time.time() + timeout
        title_re = re.compile(self.PIN_DIALOG_RE, re.I)
        desk = Desktop(backend="uia")

        while time.time() < end:
            try:
                win = desk.window(title_re=title_re)
                if win.exists() and win.is_visible():
                    return win
            except Exception:
                pass
            time.sleep(0.2)

        return None

    def preencher_senha_desktop(self, pin: str | None = None, timeout=30) -> bool:
        """
        Digita o PIN na janela nativa do Windows (quando ela surgir) e confirma com ENTER.
        Retorna True em caso de sucesso.
        """
        pin = pin if pin is not None else self._get_pin()
        if not pin:
            print("⚠️ PIN não definido (nem TOKEN_PIN, nem PIN fixo).")
            return False

        dlg = self.esperar_dialogo_pin(timeout=timeout)
        if not dlg:
            print("⚠️ Diálogo de PIN não apareceu a tempo.")
            return False

        try:
            dlg.set_focus()
            time.sleep(0.2)

            # limpa o campo (Ctrl+A + Backspace) — repete para garantir
            for _ in range(2):
                send_keys("^a{BACKSPACE}")
                time.sleep(0.05)

            # digita “devagar” para não perder caracteres
            for ch in pin:
                send_keys(ch)
                time.sleep(0.04)

            time.sleep(0.12)
            send_keys("{ENTER}")
            return True
        except Exception as e:
            print(f"⚠️ Falha ao digitar o PIN: {e}")
            return False
