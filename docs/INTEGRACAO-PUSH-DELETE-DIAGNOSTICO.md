# Exclusão de push (`queue_push_delete`) — diagnóstico do lote de 28/07/2026

Documento para o time da automação de push (Flask). Resultado de um lote real de **83 processos
(195 mensagens)** publicado em `queue_push_delete` no dia 28/07/2026, com os retornos recebidos
via callback. Objetivo: apontar **um bug de código** e **dois problemas de ambiente**, com
evidência suficiente para reproduzir.

Contrato da mensagem e do callback: [INTEGRACAO-PUSH-FLASK-AJUSTES.md](INTEGRACAO-PUSH-FLASK-AJUSTES.md).

---

## 1. O que enviamos

Publicação em `push_exchange`, routing key **`queue_push_delete`**, uma mensagem **por grau**:

```json
{
  "acao": "delete",
  "grau": "2",
  "tribunal": "13",
  "numero_processo": "0000480-72.2023.5.13.0005",
  "pagina": "", "status": "", "msg": "",
  "callbacks": [{ "url": "http://.../api/integracoes/push/retorno", "id": "<uuid>", "token": "<token>" }]
}
```

O `id` do callback é opaco (string/UUID) e deve ser **ecoado sem conversão**. Nada mudou no
contrato desde o combinado — a mesma mensagem, trocando `acao` para `create`, funciona.

## 2. Resultado do lote (195 mensagens)

| Mensagem devolvida no callback | Qtd |
|---|---|
| `Processo não localizado` | 71 |
| `Erro interno na automacao: 'AutomacaoPush' object has no attribute 'deletar_linha'` | **59** |
| `Nao foi possivel trocar para o perfil 'Advogado'. O perito pode nao ter esse perfil neste TRT.` | 28 |
| `o processo selecionado foi excluído do push.` (SUCESSO) | 18 |
| `Falha ao se autenticar no PJe` | 13 |
| *(nenhum callback recebido)* | 6 |

**Taxa de sucesso: 9%.** Em processos, 11 de 83 concluíram.

---

## 3. BUG — `'AutomacaoPush' object has no attribute 'deletar_linha'` (59 ocorrências)

O handler da exclusão chama `self.deletar_linha(...)`, método que **não existe** na classe
`AutomacaoPush`. A exceção é capturada e devolvida como "Erro interno na automacao", então
do nosso lado chega um erro limpo — mas nenhuma exclusão acontece.

**É específico de tribunal**, o que sugere caminhos de código por versão do PJe, com a rotina
de exclusão implementada só em parte deles:

| TRT | ocorrências do bug | houve algum SUCESSO nesse TRT? |
|---|---|---|
| **TRT06** | 33 | 1 |
| **TRT13** | 13 | 2 |
| **TRT10** | 10 | 2 |
| TRT19 | 3 | 3 |
| TRT01 / 05 / 07 / 09 / 21 | 0 | sim |

Exemplo reproduzível (mensagem publicada → retorno recebido):

- `0000480-72.2023.5.13.0005`, grau 2, tribunal 13 — print:
  `http://192.168.11.63:8000/screenshots/0000480-72.2023.5.13.0005_delete_ERRO_20260728_095732.png`
- `0000737-52.2020.5.06.0020`, grau 2, tribunal 6 — print:
  `http://192.168.11.63:8000/screenshots/0000737-52.2020.5.06.0020_delete_ERRO_20260728_101608.png`

**Impacto:** TRT06 e TRT13 concentram 275 dos 435 processos da fila de exclusão. Enquanto isso
não for corrigido, a maior parte do trabalho não anda.

**Pedido:** implementar/renomear `deletar_linha` na `AutomacaoPush` (ou apontar o handler para o
método correto) e cobrir os caminhos de TRT06, TRT13 e TRT10.

### Reteste em 30/07/2026 — o bug persiste

Lote de controle com **10 processos de TRT06 (20 mensagens)**, publicado hoje: **zero sucessos**.

| Retorno | Qtd |
|---|---|
| `Erro interno na automacao: 'AutomacaoPush' object has no attribute 'deletar_linha'` | 11 |
| `Processo não localizado` | 9 |

Print de hoje, para conferir que é o mesmo ponto de falha:
`http://192.168.11.63:8000/screenshots/0000975-67.2017.5.06.0023_delete_ERRO_20260730_114112.png`

Os outros ~410 processos da fila estão **retidos** até a correção — não faz sentido queimar horas de
robô num caminho que falha 100% das vezes em TRT06.

---

## 4. AMBIENTE — perfil 'Advogado' indisponível (28 ocorrências)

`Nao foi possivel trocar para o perfil 'Advogado'. O perito pode nao ter esse perfil neste TRT.`
Concentrado em **TRT05 (15)** e **TRT10 (13)**, zero nos demais. Não é código: é o certificado
usado pela automação não ter esse perfil habilitado nesses dois tribunais.

**Pedido:** confirmar qual perfil a automação exige para excluir push e se ele deveria existir
nesses TRTs — se for cadastro no tribunal, resolvemos do nosso lado.

---

## 5. AMBIENTE — `Falha ao se autenticar no PJe` (13 ocorrências)

Espalhado por 6 tribunais, sem padrão — cara de instabilidade/certificado momentâneo. Não pedimos
ação específica; entra no reprocesso. Registrado só para vocês avaliarem se cabe retry interno.

---

## 6. Callback ausente (6 mensagens)

Seis mensagens foram consumidas e **nunca receberam callback** (nem sucesso, nem erro), ficando
presas em "aguardando retorno" do nosso lado. Publicadas 28/07 às 12:10 e 13:53 (UTC); o último
callback do lote chegou às 19:13, então não foi corte de janela.

| processo | grau | tribunal |
|---|---|---|
| `13781` | 1 e 2 | TRT06 |
| `12858` | 1 e 2 | TRT06 |
| `12752` | 1 | TRT06 |
| `8573` | 1 | TRT06 |

**Pedido:** garantir callback em **todos** os caminhos de saída, inclusive exceção não tratada e
timeout do navegador. Sem ele não conseguimos distinguir "ainda rodando" de "morreu no meio", e a
mensagem fica pendurada indefinidamente. Isso já tinha sido confirmado como implementado — algum
caminho está escapando.

---

## 7. Resumo dos pedidos

1. **Corrigir `AutomacaoPush.deletar_linha`** — bloqueador, 59 falhas, atinge TRT06/13/10.
2. **Confirmar o perfil exigido** para exclusão em TRT05 e TRT10.
3. **Callback em todos os caminhos**, inclusive exceção e timeout.

Reprocessar é barato do nosso lado: as tarefas ficam registradas e republicamos só o que falhou,
sem recriar nada. Assim que houver correção, avisem que rodamos um lote pequeno de TRT06 para
validar antes de mandar o resto.
