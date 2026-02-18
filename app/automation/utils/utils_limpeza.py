import os
import shutil
import tempfile
import gc
from pathlib import Path
from datetime import datetime


def limpar_pasta_segura(caminho: Path, remover_pastas: bool = False) -> dict:
    """
    Tenta limpar o conteúdo de uma pasta (arquivos temporários, recentes, etc.)
    sem quebrar a automação em caso de erro.

    Parâmetros:
        caminho (Path): diretório a ser limpo.
        remover_pastas (bool): se True, tenta remover subpastas também.

    Retorna:
        dict com resumo:
            {
                "pasta": str,
                "arquivos_removidos": int,
                "pastas_removidas": int,
                "erros": list[str]
            }
    """
    resumo = {
        "pasta": str(caminho),
        "arquivos_removidos": 0,
        "pastas_removidas": 0,
        "erros": [],
    }

    try:
        if not caminho.exists():
            resumo["erros"].append(f"Pasta não existe: {caminho}")
            return resumo

        if not caminho.is_dir():
            resumo["erros"].append(f"Não é um diretório: {caminho}")
            return resumo

        # Percorre do nível mais interno para o mais externo
        for root, dirs, files in os.walk(caminho, topdown=False):
            root_path = Path(root)

            # Remove arquivos
            for nome_arquivo in files:
                arquivo = root_path / nome_arquivo
                try:
                    # Evita tentar remover symlinks malucos
                    if arquivo.is_file() or arquivo.is_symlink():
                        os.remove(arquivo)
                        resumo["arquivos_removidos"] += 1
                except PermissionError:
                    resumo["erros"].append(f"Sem permissão para remover arquivo: {arquivo}")
                except FileNotFoundError:
                    # Outro processo pode ter removido o arquivo
                    continue
                except OSError as e:
                    resumo["erros"].append(f"Erro ao remover arquivo {arquivo}: {e}")

            # Remove diretórios (opcional)
            if remover_pastas:
                for nome_dir in dirs:
                    dir_path = root_path / nome_dir
                    try:
                        shutil.rmtree(dir_path, ignore_errors=False)
                        resumo["pastas_removidas"] += 1
                    except PermissionError:
                        resumo["erros"].append(f"Sem permissão para remover pasta: {dir_path}")
                    except FileNotFoundError:
                        continue
                    except OSError as e:
                        resumo["erros"].append(f"Erro ao remover pasta {dir_path}: {e}")

    except Exception as e:
        resumo["erros"].append(f"Erro inesperado ao limpar {caminho}: {e}")

    return resumo


def liberar_memoria_e_limpar_temporarios(driver=None) -> dict:
    """
    Função para ser usada pela automação:
    - fecha/limpa recursos possíveis;
    - roda garbage collector;
    - limpa pastas temporárias e 'Recent'.

    Parâmetros:
        driver: instância do Selenium WebDriver (opcional).
                Se informado, tenta chamar driver.quit() com tratamento de erro.

    Retorna:
        dict com resumo geral da limpeza.
    """
    inicio = datetime.now()

    print("\n🧹 Iniciando rotina de limpeza de recursos e temporários...")
    print(f"⏱ Início: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")

    resumos = {
        "fechou_driver": False,
        "gc_coletado": True,
        "pastas_limpeza": [],
        "inicio": inicio,
        "fim": None,
        "duracao": None,
    }

    # 1) Tenta fechar o driver do Selenium, se fornecido
    if driver is not None:
        try:
            driver.quit()
            resumos["fechou_driver"] = True
            print("✅ WebDriver fechado com sucesso.")
        except Exception as e:
            resumos["fechou_driver"] = False
            print(f"⚠️ Erro ao fechar o WebDriver: {e}")

    # 2) Garbage Collector – libera objetos órfãos em memória
    try:
        gc.collect()
        print("✅ Garbage collector executado.")
    except Exception as e:
        resumos["gc_coletado"] = False
        print(f"⚠️ Erro ao executar garbage collector: {e}")

    # 3) Pastas a limpar
    pastas_alvo = []

    try:
        # Pasta TEMP do usuário/sistema (ex.: C:\\Users\\User\\AppData\\Local\\Temp)
        temp_dir = Path(tempfile.gettempdir())
        pastas_alvo.append(("TEMP (tempfile.gettempdir)", temp_dir))
    except Exception as e:
        print(f"⚠️ Não foi possível obter pasta TEMP via tempfile: {e}")

    try:
        # Pasta TEMP padrão do Windows (quando aplicável)
        win_temp = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"
        pastas_alvo.append(("Windows Temp", win_temp))
    except Exception as e:
        print(f"⚠️ Não foi possível montar caminho para Windows\\Temp: {e}")

    try:
        # Pasta Recent do usuário
        appdata = os.environ.get("APPDATA")
        if appdata:
            recent_dir = Path(appdata) / "Microsoft" / "Windows" / "Recent"
            pastas_alvo.append(("Recent", recent_dir))
    except Exception as e:
        print(f"⚠️ Não foi possível montar caminho para Recent: {e}")

    # 4) Executa limpeza nas pastas-alvo
    for rotulo, caminho in pastas_alvo:
        print(f"\n🧾 Limpando pasta: {rotulo} -> {caminho}")
        resumo_pasta = limpar_pasta_segura(caminho, remover_pastas=False)
        resumos["pastas_limpeza"].append(resumo_pasta)

        print(f"   ▸ Arquivos removidos: {resumo_pasta['arquivos_removidos']}")
        if resumo_pasta["pastas_removidas"]:
            print(f"   ▸ Pastas removidas: {resumo_pasta['pastas_removidas']}")
        if resumo_pasta["erros"]:
            print("   ▸ Ocorreram alguns erros:")
            for err in resumo_pasta["erros"]:
                print(f"     - {err}")

    fim = datetime.now()
    duracao = fim - inicio
    resumos["fim"] = fim
    resumos["duracao"] = duracao

    print("\n✅ Rotina de limpeza concluída.")
    print(f"⏱ Término: {fim.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"⏱ Duração: {str(duracao).split('.')[0]}")
    print("───────────────────────────────────────────────\n")

    return resumos
