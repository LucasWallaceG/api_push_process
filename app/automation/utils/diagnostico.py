"""Modo diagnostico do fluxo de autenticacao no PJe.

Quando o login falha, o log normal so diz "erro ao clicar X" — nao diz em QUE
tela a automacao parou. Este modulo grava url, titulo, marcadores um a um,
screenshot e HTML da pagina, para responder isso.

Opt-in pela env PJE_DIAG: com a flag desligada (padrao) nenhuma linha executa e
o comportamento de producao e identico.

Regras que este modulo respeita e nao devem ser afrouxadas:
  - NUNCA levanta excecao: diagnostico nao pode derrubar a automacao.
  - Prints em ASCII puro, inclusive nos fallbacks do except. O console do
    Windows em cp1252 nao encoda emoji e um print derrubaria justamente o
    bloco que existe para investigar a falha.
"""

import os
import re
from datetime import datetime

from selenium.webdriver.common.by import By

DIAGNOSTICO = os.getenv("PJE_DIAG", "0").strip().lower() not in ("", "0", "false", "nao", "nAo")
DIAG_DIR = os.path.abspath("diagnostico")

# Mesmos seletores do detectar_estado_pje, checados um a um: assim o
# diagnostico responde "qual marcador faltou" em vez de so dizer DESCONHECIDO.
DIAG_MARCADORES = {
    "AUTENTICADO (aria-label='Meu Painel')": (By.XPATH, '//*[@aria-label="Meu Painel"]'),
    "CODIGO_ACESSO (id='otp')": (By.ID, "otp"),
    "CERTIFICADO (link 'Seu certificado digital')": (
        By.XPATH, "//a[.//span[contains(text(), 'Seu certificado digital')]]"),
    "PDPJ (id='btnSsoPdpj')": (By.ID, "btnSsoPdpj"),
    "PAPEL/PERFIL (span.papel-usuario)": (
        By.XPATH, "//span[contains(@class, 'papel-usuario')]"),
}


def diagnostico_ativo():
    return DIAGNOSTICO


def capturar(driver, etapa, extra=""):
    """Grava url, titulo, marcadores, screenshot e HTML em ./diagnostico/.

    No-op quando PJE_DIAG esta desligada. Nunca levanta excecao.
    """
    if not DIAGNOSTICO or driver is None:
        return

    try:
        os.makedirs(DIAG_DIR, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        nome = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(etapa))[:60]
        base = os.path.join(DIAG_DIR, f"{carimbo}_{nome}")

        linhas = [f"etapa: {etapa}"]

        try:
            linhas.append(f"url: {driver.current_url}")
        except Exception as e:
            linhas.append(f"url: <indisponivel: {type(e).__name__}>")

        try:
            linhas.append(f"titulo: {driver.title}")
        except Exception as e:
            linhas.append(f"titulo: <indisponivel: {type(e).__name__}>")

        if extra:
            linhas.append(f"extra: {extra}")

        linhas.append("")
        linhas.append("marcadores:")
        for rotulo, (by, seletor) in DIAG_MARCADORES.items():
            try:
                achou = len(driver.find_elements(by, seletor))
            except Exception as e:
                achou = f"<erro: {type(e).__name__}>"
            linhas.append(f"  [{achou}] {rotulo}")

        # Import local: evita ciclo de import com scripts_pje.
        try:
            from ..Models.scripts_pje import captcha_presente
            linhas.append(f"captcha_presente: {captcha_presente(driver)}")
        except Exception as e:
            linhas.append(f"captcha_presente: <erro: {type(e).__name__}>")

        with open(base + ".txt", "w", encoding="utf-8", errors="replace") as f:
            f.write("\n".join(linhas))

        try:
            driver.save_screenshot(base + ".png")
        except Exception as e:
            print(f"[DIAG] screenshot falhou (ignorado): {type(e).__name__}")

        try:
            with open(base + ".html", "w", encoding="utf-8", errors="replace") as f:
                f.write(driver.page_source)
        except Exception as e:
            print(f"[DIAG] page_source falhou (ignorado): {type(e).__name__}")

        print(f"[DIAG] capturado: {base}")

    except Exception as e:
        print(f"[DIAG] captura falhou (ignorado): {type(e).__name__}: {e}")
