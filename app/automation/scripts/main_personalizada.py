from Models.scripts_pje import *
from datetime import datetime
from automation import automation as app
from utils_limpeza import liberar_memoria_e_limpar_temporarios


def main(peritos, trts):
    """
    Executa automação de intimações/pendências para peritos e TRTs especificados.

    Args:
        peritos (str | list[str]):
            Um nome de perito ou uma lista de nomes.
        trts (int | list[int]):
            Um TRT ou lista de TRTs. Deve conter valores entre 1 e 24.

    Regras:
        - Converte parâmetros simples para listas.
        - Valida faixa dos TRTs.
        - Garante pelo menos 1 perito e 1 TRT.
    """

    # sem driver ainda
    liberar_memoria_e_limpar_temporarios(driver=None)

    # Normalizar entrada
    if isinstance(peritos, str):
        peritos = [peritos]

    if isinstance(trts, int):
        trts = [trts]

    # Validações
    if not peritos:
        raise ValueError("É necessário informar ao menos 1 perito.")

    if not trts:
        raise ValueError("É necessário informar ao menos 1 TRT.")

    # Validar range dos TRTsWin10RB001
    for trt in trts:
        if not (1 <= trt <= 24):
            raise ValueError(f"TRT inválido ({trt}). Deve estar entre 1 e 24.")

    # Início da automação
    driver = criar_driver()
    first = True
    pjeoffice_always = False

    try:
        for perito in peritos:

            perfil = "Perito" if perito != "paula-adv" else "Advogado"
            perito_id = (
                102 if perito == "roberto" else 11 if (perito == "paula" or perito == "paula-adv") else 60
            )
            print(f'- (Perito): {perito} | Fk: {perito_id}')

            for trt in trts:

                # 🆕🔥 👉 SINCRONIZAÇÃO ANTES DE INICIAR O PROCESSO
                with app.app_context(): # <- Necessário
                    sincronizar_uma_vez(perito_id, trt)
                # ----------------------------------------------------------------

                # 🕒 Marca início da execução
                inicio_exec = datetime.now()

                print("\n━━━━━━━━━━━━━ INICIANDO EXECUÇÃO ━━━━━━━━━━━━━")
                print(f"Perito: {perito}")
                print(f"TRT: {str(trt).zfill(2)}")
                print(f"Início: {inicio_exec.strftime('%d/%m/%Y %H:%M:%S')}")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

                if first:
                    first = False

                    if abrir_pje(driver, trt) is None:
                        print('erro ao abrir pje')
                        continue

                    if clicar_botao_pdpj(driver) is None:
                        print('erro clicar botão')
                        continue

                    if clicar_certificado_digital(driver) is None:
                        print('erro clicar certificado')
                        continue

                    if pjeoffice_always is False:
                        if preencher_senha_desktop(perito) is None:
                            print('erro clicar campo senha')
                            continue

                    tentativas_max = 5
                    tentativa = 0

                    while tentativa < tentativas_max:
                        tentativa += 1
                        print(f"\nTentativa {tentativa} de {tentativas_max}")

                        codigo = gerar_codigo(perito)
                        if codigo is None:
                            print('erro ao gerar codigo')
                            continue

                        if codigo_acesso(driver, codigo) is None:
                            print('erro ao inserir codigo')
                            continue

                        if clicar_validar_codigo(driver) is None:
                            print('erro ao clicar em validar codigo')
                            continue

                        if trocar_para_perfil_perito(driver, perfil) is None:
                            print('erro ao trocar perfil')
                            continue

                        print('✅ Fluxo concluído com sucesso!')
                        break

                else:
                    print(perito)
                    if alterar_trt(driver, trt) is None:
                        print(f'erro ao acessar trt {trt}')
                        continue

                    if clicar_botao_pdpj(driver) is None:
                        print('erro clicar botão')
                        continue

                    if trocar_para_perfil_perito(driver, perfil) is None:
                        print('erro ao trocar perfil')
                        continue

                # Meu painel
                if clicar_meu_painel(driver) is None:
                    print('erro ao clicar no painel')
                    continue

                # Card correto
                card = "Intimações" if perfil == "Perito" else "Pendentes de Manifestação"
                intimacao = verificar_card_contador(driver, card)
                print(f'- (Resultado Intimações): {intimacao}')

                if intimacao is None:
                    print('❌ Não há novas intimações')
                    # ⭐ REGISTRAR EXECUÇÃO SEMPRE — inclusive quando não há intimações ⭐
                    marcar_execucao(perito_id, trt)
                    continue

                if int(intimacao) > 0:

                    if clicar_card(driver, card) is None:
                        print('❌ Erro ao clicar no card')
                        continue

                    # Processamento interno (mesma lógica atual)
                    with app.app_context():

                        if perito == "roberto":
                            # perito_id = 102
                            func = get_intimacoes_dict_list

                        elif perito == "paula":
                            # perito_id = 11
                            func = get_intimacoes_dict_list

                        elif perito == "paula-adv":
                            # perito_id = 11
                            func = get_processos_advogado

                        else:
                            # perito_id = 60
                            func = get_intimacoes_dict_list

                        if func(driver, perito_id) is None:
                            print('❌ Erro ao verificar TR')
                            continue

                else:
                    print('ℹ️ TRT sem intimações.')

                # 🕒 término
                termino_exec = datetime.now()
                duracao_fmt = str(termino_exec - inicio_exec).split(".")[0]

                print("━━━━━━━━━━━━━ FINALIZADO ━━━━━━━━━━━━━")
                print(f"Perito: {perito}")
                print(f"TRT: {str(trt).zfill(2)}")
                print(f"Término: {termino_exec.strftime('%d/%m/%Y %H:%M:%S')}")
                print(f"Duração: {duracao_fmt}")
                print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

                # ⭐ REGISTRAR EXECUÇÃO SEMPRE — inclusive quando não há intimações ⭐
                marcar_execucao(perito_id, trt)

    finally:
        liberar_memoria_e_limpar_temporarios(driver=driver)


if __name__ == "__main__":
    main(
        peritos=["roberto"],
        trts=[1, 3, 5, 6, 7, 9, 10, 13, 19, 21]
    )