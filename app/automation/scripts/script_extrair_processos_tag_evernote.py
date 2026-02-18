import os
import shutil
import xlsxwriter
import xml.etree.ElementTree as ET


def main():

    indice_1 = 0
    lista_unica = []

    # Planilha Evernote
    local_planilha_base = fr"{os.getcwd()}\Evernote.xlsx"
    workbook_evernote = xlsxwriter.Workbook(local_planilha_base)
    planilha_evernote = workbook_evernote.add_worksheet("Planilha1")

    # SECUNDARIO
    evernote_raiz = fr"{os.getcwd()}\Tag_evernote_excluir_push"
    contador_notas = 0

    for root_dir, subdirs, files in os.walk(evernote_raiz):

        for file in files:
            print(f'- (FILE): {file}')

            if not '.enex' in file: continue

            caminho_absoluto = os.path.join(root_dir, file)
            # Extraindo o penúltimo elemento do caminho
            penultimo_diretorio = os.path.basename(os.path.dirname(caminho_absoluto))

            print(f"- (Arquivo): {file}")
            print(f"  (Diretório): {penultimo_diretorio}")
            print(f"  (Full Path): {caminho_absoluto}\n======================================\n")
            try:
                tree = ET.parse(caminho_absoluto)
                root = tree.getroot()
            except ET.ParseError:
                print(f"[ERROR] - Arquivo ENEX corrompido → {caminho_absoluto}")
                root = None

            planilha_evernote.write(0, 0, "NUMERO_PROCESSO")
            planilha_evernote.write(0, 1, "ID_PROCESSO")
            planilha_evernote.write(0, 2, "STATUS")
            planilha_evernote.write(0, 3, "MSG")

            for i in range(1, len(root)):
                nota = root[i].find('title').text
                if not nota in lista_unica:
                    lista_unica.append(nota)

                    conteudo = nota.split("_", 1)[1].split(" ", 1)[0]
                    planilha_evernote.write(indice_1, 0, conteudo)

                    # Planilha 2
                    id_processo = nota.split("_")[0].strip()
                    if id_processo:
                        # Grava também o número do processo na primeira planilha
                        planilha_evernote.write(indice_1, 1, id_processo)
                        log_content = f"---- [{id_processo}] - {nota}\n"
                    else:
                        # Grava a nota completa caso o número do processo não seja encontrado
                        planilha_evernote.write(indice_1, 1, nota)
                        log_content = f"---- [{nota}\n"

                    print(f'- [LOG]: {log_content}')
                    # gravar_conteudo_arquivo_txt(log_content)
                    indice_1 += 1
                    contador_notas += 1

    # Salvar e fechar Planilhas
    workbook_evernote.close()
    print(f" - (Total de Notas): {contador_notas}")

    # SECUNDARIO
    shutil.copy(local_planilha_base, evernote_raiz)


if __name__ == "__main__":
    main()