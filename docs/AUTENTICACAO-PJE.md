# Autenticação no PJe — como este serviço evita o captcha

Aplicação, neste projeto, da estratégia descrita em
[CONTEXTO-AUTENTICACAO-PJE.md](CONTEXTO-AUTENTICACAO-PJE.md). Aqui ficam só as
diferenças e o procedimento de operação.

## Por que o risco é maior aqui

Na automação de intimações um processo longo percorre vários TRTs. Aqui cada
mensagem da fila cria **um driver novo** (`criar_driver` em `start_automation`),
então o ciclo "abrir → autenticar" acontece a cada processo. Sem sessão
persistente no perfil, isso é exatamente o padrão que o Keycloak trata como
força bruta — e o captcha aparece.

## O que existe no código

| Peça | Onde |
|---|---|
| Perfil fixo por serviço + `parent.lock` + `set_page_load_timeout` | `criar_driver`, `_liberar_lock_perfil` — [scripts_pje.py](../app/automation/Models/scripts_pje.py) |
| Detecção de captcha (entidades HTML + acentos normalizados) | `captcha_presente`, `MARCADORES_CAPTCHA` |
| Estado da tela, com CAPTCHA checado primeiro | `detectar_estado_pje` |
| Laço de autenticação, OTP limitado e espaçado, espera após o PDPJ | `garantir_autenticacao`, `_aguardar_saida_do_pdpj` |
| Motivo da falha no callback/dashboard | `ultimo_motivo_autenticacao` → [main.py](../app/automation/main.py) |
| Re-semeadura manual | [login_manual.bat](../login_manual.bat) |
| Modo diagnóstico (opt-in) | [diagnostico.py](../app/automation/utils/diagnostico.py), [diagnostico_pje.bat](../diagnostico_pje.bat) |

## Duas diferenças em relação ao documento de origem

**Um perfil por serviço, não um só.** Os consumers de cadastro e exclusão rodam
em paralelo, e o Firefox não abre o mesmo perfil duas vezes. Cada um define
`FIREFOX_PROFILE` (`cadastro` / `exclusao`), e o perfil vive em
`firefox_profiles/<nome>/`. Consequência prática: **re-semear um perfil não
re-semeia o outro** — rode o `login_manual.bat` uma vez para cada.

**Nada de `taskkill /IM firefox.exe`.** A receita genérica mata todos os Firefox
quando o `parent.lock` não sai. Aqui isso derrubaria o navegador do outro
consumer (ou um login manual em andamento). `_liberar_lock_perfil` remove só o
lock órfão; se ele estiver em uso, avisa e deixa o Firefox reportar.

## Operação

**Sessão expirou / apareceu captcha.** O callback e o dashboard mostram a
mensagem completa (`MSG_CAPTCHA`), não só "Falha ao se autenticar". Então:

1. Pare o consumer do perfil afetado.
2. `login_manual.bat cadastro 6` (ou `exclusao`), faça o login resolvendo o
   captcha até cair no painel, feche o Firefox.
3. Reinicie o consumer.

**Login falhando sem captcha.** `diagnostico_pje.bat consumer_cadastrar_push.py`
e olhe `diagnostico/`: o `.txt` diz qual marcador faltou e o `.png`/`.html`
mostram a tela. Com `PJE_DIAG` desligada nada disso é gerado.

## Como validar

1. **Sessão viva:** com o perfil re-semeado, enfileirar 2+ processos. O log deve
   mostrar `[AUTH] Estado detectado: AUTENTICADO` (ou `PDPJ` → `AUTENTICADO`) e
   **nenhum** envio de OTP.
2. **Sessão morta:** apagar `firefox_profiles/<nome>/` e enfileirar um processo.
   Deve percorrer `PDPJ` → `CERTIFICADO` → `CODIGO_ACESSO` → `AUTENTICADO`, com
   no máximo 3 OTPs espaçados de 20s.
3. **Captcha:** a automação para na hora, o callback sai como `ERRO` com a
   orientação de re-semeadura e nenhum novo login é tentado.
4. **Flag off:** sem `PJE_DIAG`, a pasta `diagnostico/` não é criada e o log não
   tem linha `[DIAG]`.

## Pendência conhecida

Os scripts legados [script_acessar_pje.py](../app/automation/utils/script_acessar_pje.py)
e [main_personalizada.py](../app/automation/scripts/main_personalizada.py) ainda
chamam os passos de login diretamente, sem passar por `garantir_autenticacao` —
violam a regra de ouro. Nenhum deles participa do fluxo dos consumers hoje
(`main.py` importa `preparar_ambiente` mas não o usa, e o módulo sequer tem os
imports de que precisa), então não foram alterados. Se algum voltar a ser usado,
migre-o para `garantir_autenticacao` antes.
