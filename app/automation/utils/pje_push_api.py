"""
Acesso direto a API de Push do PJe (pje-comum-api), reaproveitando a sessao ja
autenticada pelo Selenium (cookies + X-XSRF-TOKEN).

Usado para EXCLUIR (inativar) um registro de push por codigo, sem precisar
navegar/paginar a tela — muito mais rapido e estavel que a varredura de UI.

Contrato observado no PJe (vale para qualquer TRT, muda so o host):
    PUT {host}/pje-comum-api/api/push/inativar
        Content-Type: application/json
        Cookie: access_token=...; Xsrf-Token=...; ...
        X-XSRF-TOKEN: <valor do cookie Xsrf-Token>
        body: [<codigo>]            # array de IDs internos do registro
    -> 204 No Content = sucesso
"""
import json
import requests
from urllib.parse import urlparse


def _api_base(driver):
    """
    Deriva o host da API a partir da URL atual do Selenium.
    Funciona em qualquer TRT (o host da sessao ja e o do tribunal correto).
    Retorna algo como 'https://pje.trt1.jus.br' ou None se indisponivel.
    """
    try:
        p = urlparse(driver.current_url)
    except Exception:
        return None
    if not p.scheme or not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}"


def _sessao_requests(driver):
    """
    Monta uma requests.Session com os cookies da sessao autenticada do Selenium
    (inclui HttpOnly) e o header X-XSRF-TOKEN (valor do cookie Xsrf-Token, exigido
    pela API como protecao CSRF). Retorna (session, base) ou (None, None).
    """
    base = _api_base(driver)
    if not base:
        return None, None

    sess = requests.Session()
    xsrf = None
    try:
        cookies = driver.get_cookies()
    except Exception:
        cookies = []

    for c in cookies:
        nome = c.get("name")
        valor = c.get("value")
        if not nome:
            continue
        try:
            sess.cookies.set(nome, valor)
        except Exception:
            continue
        if nome.lower() == "xsrf-token":
            xsrf = valor

    sess.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": f"{base}/pjekz/push",
        "Origin": base,
    })
    if xsrf:
        sess.headers["X-XSRF-TOKEN"] = xsrf

    return sess, base


def _extrair_codigo(resp):
    """Extrai o codigo (int) da resposta, seja numero puro ou JSON."""
    txt = (resp.text or "").strip().strip('"')
    if not txt:
        return None
    if txt.isdigit():
        return int(txt)
    try:
        data = resp.json()
    except Exception:
        return None
    if isinstance(data, int):
        return data
    if isinstance(data, dict):
        for k in ("id", "codigo", "idPush", "idAssinatura", "idProcesso"):
            v = data.get(k)
            if v:
                return v
    if isinstance(data, list) and data:
        primeiro = data[0]
        if isinstance(primeiro, dict):
            return primeiro.get("id") or primeiro.get("codigo")
        if isinstance(primeiro, (int, str)):
            return primeiro
    return None


def consultar_codigo_push(driver, numero_processo, timeout=20):
    """
    Consulta o codigo (ID da assinatura de push) de um processo, via API, na
    sessao/grau atual do Selenium.

    GET {host}/pje-comum-api/api/push/processo?numeroProcesso=X

    Retorna o codigo (int) ou None. Loga o corpo bruto da resposta para permitir
    confirmar/ajustar o formato durante os testes.
    """
    sess, base = _sessao_requests(driver)
    if not sess:
        return None

    url = f"{base}/pje-comum-api/api/push/processo"
    try:
        resp = sess.get(url, params={"numeroProcesso": numero_processo}, timeout=timeout)
    except Exception as e:
        print(f"⚠️ [PUSH-API] falha ao consultar codigo: {e}")
        return None

    print(f"🔎 [PUSH-API] consulta codigo | HTTP {resp.status_code} | body={resp.text[:200]!r}")
    if resp.status_code != 200:
        return None

    return _extrair_codigo(resp)


def inativar_push_por_codigo(driver, codigo, timeout=20):
    """
    Inativa (exclui) um registro de push pelo codigo (ID interno) fornecido pelo
    tarefas-jrs, via API — sem paginar a tela.

    Retorna dict {'sucesso': bool, 'mensagem': str}, compativel com
    normalizar_resultado().
    """
    try:
        codigo_int = int(codigo)
    except (TypeError, ValueError):
        return {"sucesso": False, "mensagem": f"codigo invalido para API: {codigo!r}"}

    sess, base = _sessao_requests(driver)
    if not sess:
        return {"sucesso": False, "mensagem": "Sessao de API indisponivel (sem cookies/URL)"}

    xsrf_ok = "X-XSRF-TOKEN" in sess.headers
    if not xsrf_ok:
        # Sem o token CSRF a API costuma responder 403; loga mas ainda tenta.
        print("⚠️ [PUSH-API] cookie Xsrf-Token nao encontrado na sessao do Selenium.")

    url = f"{base}/pje-comum-api/api/push/inativar"

    try:
        resp = sess.put(url, data=json.dumps([codigo_int]), timeout=timeout)
    except Exception as e:
        return {"sucesso": False, "mensagem": f"Falha de rede ao inativar via API: {e}"}

    if resp.status_code in (200, 204):
        return {
            "sucesso": True,
            "mensagem": f"processo inativado no push via API (codigo {codigo_int})",
        }

    corpo = (resp.text or "")[:300]
    return {
        "sucesso": False,
        "mensagem": f"API inativar retornou HTTP {resp.status_code}: {corpo}",
    }
