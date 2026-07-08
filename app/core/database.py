import os
import sqlite3
import threading
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'db-sqlite')
DB_PATH = os.path.join(DB_DIR, 'push_monitor.db')

_local = threading.local()


def _get_conn():
    """Retorna conexao SQLite thread-local (uma por thread)."""
    if not hasattr(_local, 'conn') or _local.conn is None:
        os.makedirs(DB_DIR, exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
    return _local.conn


def init_db():
    """Cria a tabela de registros se nao existir."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem       INTEGER,
            processo    TEXT,
            trt         TEXT,
            grau        TEXT,
            acao        TEXT,
            status      TEXT,
            msg         TEXT,
            screenshot  TEXT,
            req_id      TEXT,
            data_hora   TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_registros_data_hora
        ON registros (data_hora)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_registros_processo_acao
        ON registros (processo, acao)
    """)

    # Migracao: adiciona colunas novas em bancos antigos que nao as possuem.
    colunas = {row["name"] for row in conn.execute("PRAGMA table_info(registros)")}
    if "screenshot" not in colunas:
        conn.execute("ALTER TABLE registros ADD COLUMN screenshot TEXT")
    if "req_id" not in colunas:
        conn.execute("ALTER TABLE registros ADD COLUMN req_id TEXT")

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_registros_req_id
        ON registros (req_id)
    """)

    conn.commit()


def salvar_registro(registro: dict):
    """
    Insere ou atualiza registro no banco.

    Deduplicacao:
    - Se o registro traz 'req_id' (id unico da requisicao), o upsert e por req_id.
      Assim o ciclo de vida da MESMA requisicao (AGUARDANDO -> PROCESSANDO -> final)
      atualiza uma unica linha, e cada NOVA requisicao vira uma NOVA linha.
    - Sem req_id (legado), colapsa apenas quando a ultima linha do mesmo
      (processo, acao) ainda estiver em andamento; caso contrario, insere nova.
    """
    conn = _get_conn()
    req_id = registro.get("req_id")

    if req_id:
        cursor = conn.execute(
            "SELECT id FROM registros WHERE req_id = ?",
            (req_id,),
        )
    else:
        cursor = conn.execute(
            "SELECT id FROM registros WHERE processo = ? AND acao = ? "
            "AND status IN ('AGUARDANDO', 'PROCESSANDO') "
            "ORDER BY id DESC LIMIT 1",
            (registro["processo"], registro["acao"]),
        )
    row = cursor.fetchone()

    if row:
        # Preserva o screenshot existente quando o novo registro nao traz um
        # (ex.: atualizacao de status intermediaria sem novo print).
        set_cols = ["status = ?", "msg = ?", "data_hora = ?", "trt = ?", "grau = ?", "ordem = ?"]
        params = [
            registro["status"],
            registro["msg"],
            registro["data_hora"],
            registro["trt"],
            registro["grau"],
            registro["ordem"],
        ]
        if registro.get("screenshot"):
            set_cols.append("screenshot = ?")
            params.append(registro["screenshot"])
        params.append(row["id"])

        conn.execute(
            f"UPDATE registros SET {', '.join(set_cols)} WHERE id = ?",
            params,
        )
    else:
        conn.execute(
            """INSERT INTO registros (ordem, processo, trt, grau, acao, status, msg, screenshot, req_id, data_hora)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                registro["ordem"],
                registro["processo"],
                registro["trt"],
                registro["grau"],
                registro["acao"],
                registro["status"],
                registro["msg"],
                registro.get("screenshot"),
                registro.get("req_id"),
                registro["data_hora"],
            ),
        )
    conn.commit()


def buscar_registros(data_inicio: str | None = None, data_fim: str | None = None):
    """
    Busca registros filtrados por periodo.
    data_inicio e data_fim no formato 'YYYY-MM-DD'.
    Se nenhum for informado, retorna registros do dia atual.
    """
    conn = _get_conn()

    if not data_inicio and not data_fim:
        data_inicio = datetime.now().strftime("%Y-%m-%d")
        data_fim = data_inicio

    conditions = []
    params = []

    if data_inicio:
        conditions.append("date(data_hora) >= ?")
        params.append(data_inicio)

    if data_fim:
        conditions.append("date(data_hora) <= ?")
        params.append(data_fim)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = conn.execute(
        f"SELECT * FROM registros {where} ORDER BY data_hora DESC", params
    ).fetchall()

    return [dict(r) for r in rows]