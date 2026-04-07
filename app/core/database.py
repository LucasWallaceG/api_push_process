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
    conn.commit()


def salvar_registro(registro: dict):
    """Insere ou atualiza registro no banco (upsert por processo+acao)."""
    conn = _get_conn()
    cursor = conn.execute(
        "SELECT id FROM registros WHERE processo = ? AND acao = ?",
        (registro["processo"], registro["acao"]),
    )
    row = cursor.fetchone()

    if row:
        conn.execute(
            """UPDATE registros
               SET status = ?, msg = ?, data_hora = ?, trt = ?, grau = ?, ordem = ?
               WHERE id = ?""",
            (
                registro["status"],
                registro["msg"],
                registro["data_hora"],
                registro["trt"],
                registro["grau"],
                registro["ordem"],
                row["id"],
            ),
        )
    else:
        conn.execute(
            """INSERT INTO registros (ordem, processo, trt, grau, acao, status, msg, data_hora)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                registro["ordem"],
                registro["processo"],
                registro["trt"],
                registro["grau"],
                registro["acao"],
                registro["status"],
                registro["msg"],
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