import os
import json
from datetime import datetime
from Models.scripts_pje import *
from pagepush.script_data_push import AutomacaoPush
from script_salvar_log_return_csv import salvar_log_trts_csv
from utils_limpeza import liberar_memoria_e_limpar_temporarios

# Definir data da execução (uma vez)
DATA_EXECUCAO = datetime.now().strftime("%Y-%m-%d")
ARQUIVO_JSON = f"processos_push_{DATA_EXECUCAO}.json"

# Funções utilitárias de leitura/gravação (checkpoint)
def carregar_snapshot_dia(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar_snapshot_dia(path, dados):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)


def main():


    driver = criar_driver()
    peritos = ["paula"]
    log_trts = {}
    dados_do_dia = carregar_snapshot_dia(ARQUIVO_JSON)

    # 🔑 cria set de chaves a partir do que já foi salvo hoje
    chaves_unicas = {
        f"{item['tribunal']}|{item['numero_processo']}"
        for item in dados_do_dia
    }

    try:
        for perito in peritos:

            perfil = "Advogado"

            for trt in range(1, 25):

                objAutomacaoPush = AutomacaoPush(driver, trt)

                if abrir_pje(driver, trt) is None:
                    continue

                if not garantir_autenticacao(driver, perito):
                    print("❌ Falha ao autenticar")
                    continue

                if clicar_meu_painel(driver) is None:
                    continue

                garantir_perfil(driver, perfil)

                try:
                    dados_trt, total_tela = objAutomacaoPush.function_main_push(
                        chaves_unicas=chaves_unicas,
                        data_execucao=DATA_EXECUCAO
                    )
                except RuntimeError as e:
                    print(f"[RECOVERY] {e}")
                    clicar_meu_painel(driver)
                    continue

                # incrementa snapshot do dia
                dados_do_dia.extend(dados_trt)

                # 🔥 checkpoint imediato
                salvar_snapshot_dia(ARQUIVO_JSON, dados_do_dia)

                tribunal = f"TRT{trt}"
                log_trts[tribunal] = {
                    "extraidos": len(dados_trt),
                    "total_tela": total_tela
                }

                print(f"✅ TRT {trt} salvo. Total acumulado: {len(dados_do_dia)}")

        # 🔥 salva auditoria no final
        salvar_log_trts_csv(log_trts)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()