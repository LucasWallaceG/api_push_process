"""
Captura e armazenamento de screenshots da automação.

Os prints ficam em <raiz-do-projeto>/screenshots e sao servidos pela API Flask
via a rota /screenshots/<arquivo>. O nome do arquivo e vinculado ao processo,
acao e status para facilitar a rastreabilidade.
"""
import os
import re
from datetime import datetime

# <raiz-do-projeto>/screenshots  (app/core/screenshots.py -> ../../screenshots)
SCREENSHOT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "screenshots"
)
SCREENSHOT_DIR = os.path.abspath(SCREENSHOT_DIR)

# Prefixo da URL publica (rota Flask)
URL_PREFIX = "/screenshots"


def _slug(texto: str) -> str:
    """Normaliza um texto para uso seguro em nome de arquivo."""
    texto = (texto or "").strip()
    return re.sub(r"[^A-Za-z0-9._-]+", "-", texto) or "sem-valor"


def capturar_screenshot(driver, processo, acao, status) -> str:
    """
    Salva um print da tela atual vinculado ao processo.

    Retorna a URL relativa (ex.: '/screenshots/0000511-...create_ERRO_2026....png')
    para ser exibida no dashboard, ou '' se nao for possivel capturar.
    """
    if driver is None:
        return ""

    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)

        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome = f"{_slug(processo)}_{_slug(acao)}_{_slug(status)}_{carimbo}.png"
        caminho = os.path.join(SCREENSHOT_DIR, nome)

        # Print da AREA DE TRABALHO INTEIRA (todos os monitores), para nao
        # cortar trechos da pagina e incluir a barra de tarefas (data/hora da
        # ocorrencia). O navegador roda visivel/maximizado, entao o desktop
        # reflete a tela do PJe. Se falhar (ex.: ambiente sem display), cai
        # para o print do proprio navegador via Selenium.
        capturado = False
        try:
            from PIL import ImageGrab

            imagem = ImageGrab.grab(all_screens=True)
            imagem.save(caminho)
            capturado = True
        except Exception as e:
            print(f"⚠️ Print do desktop indisponivel ({e}); usando print do navegador.")

        if not capturado:
            driver.save_screenshot(caminho)

        print(f"📸 Screenshot salvo: {nome}")

        return f"{URL_PREFIX}/{nome}"

    except Exception as e:
        print(f"⚠️ Falha ao capturar screenshot: {e}")
        return ""
