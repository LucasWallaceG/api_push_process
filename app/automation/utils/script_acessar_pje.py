# from .Models.scripts_pje import *
from selenium.common.exceptions import WebDriverException


def sessao_ativa(driver, timeout=5):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.ID, "btnPDPJ"))  # ajuste se necessário
        )
        return True
    except:
        return False


def driver_ativo(driver):
    try:
        _ = driver.current_url
        return True
    except WebDriverException:
        return False


def autenticar_se_necessario(driver, perito):
    """
    Garante que o usuário esteja autenticado no PJe.
    Se já estiver logado, não faz nada.
    """

    print("🔐 Sessão inativa. Iniciando autenticação...")

    if clicar_botao_pdpj(driver) is None:
        raise Exception("Erro ao clicar no botão PDPJ")

    if clicar_certificado_digital(driver) is None:
        raise Exception("Erro ao selecionar certificado")

    try:
        if preencher_senha_desktop(perito) is None:
            raise Exception("Erro ao preencher senha do certificado")
    except Exception as e:
        print(f'- (except)[preencher_senha_desktop]: {e}')

    for tentativa in range(1, 6):
        print(f"🔑 Tentativa {tentativa}/5")

        codigo = gerar_codigo(perito)
        if codigo is None:
            continue

        if codigo_acesso(driver, codigo) is None:
            continue

        if clicar_validar_codigo(driver) is None:
            continue

        print("✅ Autenticação concluída")
        return True

    raise Exception("Falha ao autenticar no PJe")


def preparar_ambiente(driver, automation, trt, perito):
    """
    Prepara o ambiente do PJe e retorna o contexto:
    - 'pje-atual' → já estava no TRT correto
    - None        → houve troca de TRT / novo login
    """

    context = automation.garantir_trt(trt)
    print(f'- (Contexto): {context}')
    print(f'- (Primeira Iteração)[1]: {automation.first_execution}')

    # sempre que garantir_trt faz driver.get(), cai em /login.seam
    if automation.first_execution:
        autenticar_se_necessario(driver, perito)
    print(f'- (Primeira Iteração)[2]: {automation.first_execution}')

    # 🔑 SÓ clicar PDPJ se houve troca de URL
    if context != 'pje-atual' and automation.first_execution is False:
        if clicar_botao_pdpj(driver) is None:
            raise Exception("Erro ao acessar PDPJ")

        try:
            if clicar_meu_painel(driver) is None:
                raise Exception("Erro ao acessar Meu Painel")
        except Exception:
            print(f'- (except)[preparar_ambiente_clicar_meu_painel]')
            autenticar_se_necessario(driver, perito)

    automation.first_execution = False
    return context


def main_autentication(driver, first=True):

    perito = "paula"
    while True:
        if first:
            first = False

            if clicar_botao_pdpj(driver) is None:
                print('erro clicar botão')
                continue

            if clicar_certificado_digital(driver) is None:
                print('erro clicar certificado')
                continue

            if preencher_senha_desktop(perito) is None:
                print('erro clicar campo senha')
                continue

            tentativas_max = 5
            tentativa = 0

            while tentativa < tentativas_max:
                tentativa += 1
                print(f"\nTentativa {tentativa} de {tentativas_max}")


                # time.sleep(15)
                # break

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

                print('✅ Fluxo concluído com sucesso!')
                break
            else:
                print('❌ Todas as tentativas falharam. Encerrando execução.')

        else:
            break