from pagepush.script_data_push import AutomacaoPush


def main(automation: AutomacaoPush, processo: str, grau="primeirograu"):
    # garante que está no TRT correto
    automation.garantir_trt(automation.trt, grau)

    # cadastra o processo
    automation.function_main_cad_push(processo)

    return {"processo": processo, "status": "ok"}


if __name__ == '__main__':
    main()