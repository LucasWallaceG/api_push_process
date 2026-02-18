import pandas as pd
import requests
import time
from datetime import datetime

URL_AUTOMACAO = "http://192.168.11.38:9000/automacao/rabbit/push/add"
DELAY = 5
ARQUIVO_CSV = "push_pendente_13022026_principais.csv"

LOG_ERROS_TRIBUNAL = "log_trt_invalido.txt"
LOG_ERROS_ENVIO = "log_envio_400.txt"

# =========================
# Leitura CSV
# =========================

df = pd.read_csv(ARQUIVO_CSV, dtype=str)
print(df.columns)
df["numero_processo"] = df["processo_assoc"].astype(str).str.strip()


# =========================
# Extração TRT robusta
# =========================
def extrair_trt(numero_processo: str):
    try:
        partes = numero_processo.split(".")
        if len(partes) < 5:
            return None

        trt = int(partes[-2])
        return trt if 1 <= trt <= 24 else None
    except Exception:
        return None


df["trt"] = df["numero_processo"].apply(extrair_trt)

# =========================
# LOG TRT inválido
# =========================
df_invalidos = df[df["trt"].isna()]

if not df_invalidos.empty:
    with open(LOG_ERROS_TRIBUNAL, "a", encoding="utf-8") as f:
        for p in df_invalidos["numero_processo"]:
            f.write(f"[{datetime.now()}] TRT inválido: {p}\n")

df_validos = df.dropna(subset=["trt"]).sort_values("trt")

print(f"📦 Total de processos válidos: {len(df_validos)}")
print(f"⚠️ TRT inválidos ignorados: {len(df_invalidos)}")

# =========================
# Envio RabbitMQ
# =========================
count = 1
for _, row in df_validos.iterrows():
    payload = {
        "trt": int(row["trt"]),
        "numero_processo": row["numero_processo"],
        "grau": ["primeirograu"],
    }

    print(f'- (Nº): {count}')
    print(f"➡️ Enviando TRT {payload['trt']} | {payload['numero_processo']}")

    try:
        r = requests.post(URL_AUTOMACAO, json=payload, timeout=3)

        if not r.status_code in [200, 202]:
            with open(LOG_ERROS_ENVIO, "a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.now()}] STATUS {r.status_code} | TRT {payload['trt']} | {payload['numero_processo']}\n"
                )

            print(f"❌ ERRO {r.status_code}")
        else:
            print("✅ OK")

    except Exception as e:
        with open(LOG_ERROS_ENVIO, "a", encoding="utf-8") as f:
            f.write(
                f"[{datetime.now()}] EXCEPTION | {payload['numero_processo']} | {e}\n"
            )
        print(f"❌ Exception: {e}")

    time.sleep(DELAY)
    count += 1
