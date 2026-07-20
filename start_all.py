import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


def abrir_terminal(titulo, script):
    caminho = os.path.join(BASE_DIR, script)
    ps_cmd = f"$Host.UI.RawUI.WindowTitle = '{titulo}'; & '{PYTHON}' '{caminho}'"
    subprocess.Popen(
        ['powershell', '-NoExit', '-Command', ps_cmd],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        cwd=BASE_DIR,
    )


if __name__ == "__main__":
    abrir_terminal("Dashboard Flask", "main.py")
    abrir_terminal("Consumer Cadastro", "consumer_cadastrar_push.py")
    abrir_terminal("Consumer Exclusao", "consumer_excluir_push.py")

    print("Iniciando servicos...")
    print("  [1] Dashboard Flask      -> http://localhost:8000")
    print("  [2] Consumer Cadastro    -> queue_push_insert")
    print("  [3] Consumer Exclusao    -> queue_push_delete")
