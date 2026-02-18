from selenium.webdriver.common.by import By
# from selenium.webdriver.common.devtools.v138.fetch import continue_with_auth
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.common.exceptions import TimeoutException
# from automation.tools.tools import Tools
import time, re


class AutomacaoPush:
# class AutomacaoPush(Tools):


    def abrir(self, url: str, processo: str):
        try:
            self.driver.get(url)
        except Exception as erro:
            print(f"[nav] Não foi possível logar: {erro}.")
            return {'status': 'erro', 'processo': processo}


    def login(self, url: str, processo: str):

        BTN_MENU = (By.ID, "botao-menu")
        BTN_ENTRAR = (By.ID, "btnSsoPdpj")
        BTN_CERTIFICADO = (By.CSS_SELECTOR, ".botao-certificado-titulo")
        CAMPO_CERTIFICADO = (By.ID, "otp")
        BTN_VALIDAR = (By.ID, "kc-login")

        try:

            # self.abrir(url, processo)
            # self.click(BTN_ENTRAR)
            # self.click(BTN_CERTIFICADO)

            time.sleep(3)

            if self.click(BTN_MENU) is None:

                print("[login] login não confirmado após validar -> tentar de novo (gerar novo código)")
                tentativas_max = 5
                tentativa = 0

                while tentativa < tentativas_max:
                    tentativa += 1
                    print(f"[login] tentativa {tentativa}/{tentativas_max}")
                    codigo = self.gerar_codigo()
                    print(f"[login] codigo gerado: {codigo}")
                    if not codigo:
                        print("[login] gerar_codigo retornou None -> gerar outro")
                        time.sleep(1)
                        continue
                    time.sleep(3)
                    if self.escrever_campo(CAMPO_CERTIFICADO, codigo, True) is None:
                        print(f"[login] não encontrou/não conseguiu escrever no campo OTP")
                        continue
                    time.sleep(3)

                    if self.click(BTN_VALIDAR) is None:
                        print("[login] click validar retornou None -> tentar novamente")
                        time.sleep(1)
                        continue

                    time.sleep(3)
                    if self.click(BTN_MENU) is None:
                        print("[login] login não confirmado após validar -> tentar de novo (gerar novo código)")
                        continue

                    break
                else:
                    print(f"[nav] Não foi possível logar.")
                    return {'status': 'erro'}

            time.sleep(3)

        except Exception as erro:
            print(f"[nav] Não foi possível logar: {erro}.")
            return {'status': 'erro', 'processo': processo}

    def fluxo(self, processo: str):

        # --- locators ---
        BTN_CADASTRO = (By.XPATH, "//*[contains(normalize-space(text()), 'Cadastro')]")
        BTN_PUSH = (By.XPATH, "//*[contains(normalize-space(text()), 'PUSH')]")
        BTN_ADICIONAR = (By.CSS_SELECTOR, "button[aria-label='Adicionar Processos para Acompanhamento']")
        BTN_INPUT = (By.ID, "inputNumeroProcesso")
        BTN_INCLUIR = (By.CSS_SELECTOR, "button[aria-label='Incluir'].mat-raised-button:not(.mat-button-disabled)")


        time.sleep(5)

        print("[nav] Clicando BTN_CADASTRO…")
        if self.click(BTN_CADASTRO)is None:
            print(f"[nav] Não foi possível clicar no BTN_CADASTRO")
            return {'status': 'erro', 'processo': processo}

        time.sleep(3)


        print("[nav] Clicando BTN_PUSH…")
        if self.click(BTN_PUSH)is None:
            print(f"[nav] Não foi possível clicar no BTN_PUSH:")
            return {'status': 'erro', 'processo': processo}
        time.sleep(3)


        print("[nav] Clicando BTN_ADICIONAR…")
        if self.click(BTN_ADICIONAR) is None:
            print(f"[nav] Não foi possível clicar no BTN_ADICIONAR")
            return {'status': 'erro', 'processo': processo}
        time.sleep(3)

        print("[nav] Clicando BTN_INPUT…")
        if self.click(BTN_INPUT)is None:
            print(f"[nav] Não foi possível clicar no BTN_PAGINA")
            return {'status': 'erro', 'processo': processo}
        time.sleep(3)

        try:
            print("[nav] Digitando BTN_INPUT…")
            self.escrever_campo(BTN_INPUT, processo, True);    time.sleep(3)
        except Exception as erro:
            print(f"[nav] Não foi possível digitar no BTN_PAGINA")
            return {'status': 'erro', 'processo': processo}

        time.sleep(3)
        print("[nav] Digitando BTN_INCLUIR…")
        if self.click(BTN_INCLUIR) is None:
            print(f"[nav] Não foi possível digitar no BTN_PAGINA")
            return {'status': 'erro', 'processo': processo}
        time.sleep(3)