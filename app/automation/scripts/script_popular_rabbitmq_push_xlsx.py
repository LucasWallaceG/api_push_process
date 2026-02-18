import pandas as pd
import requests
import time

URL_AUTOMACAO = "http://192.168.11.38:9000/automacao/rabbit/push/add"
DELAY = 5  # segundos

df = pd.read_excel("Ausente_cadastro_push.xlsx")

for _, row in df.iterrows():
    numero_processo = str(row["Número Processo"]).strip()

    # TRT extraído do número do processo (mesma lógica do Django)
    try:
        trt = int(numero_processo.split(".")[3])
    except Exception:
        print(f"❌ TRT inválido: {numero_processo}")
        continue

    payload = {
        "trt": trt,
        "numero_processo": numero_processo,
        "grau": ["primeirograu"],  # 🔥 PADRÃO FIXO
    }

    print(f"➡️ Enviando: {payload}")

    try:
        r = requests.post(URL_AUTOMACAO, json=payload, timeout=10)
        print(f"STATUS: {r.status_code}")
    except Exception as e:
        print("❌ Erro:", e)

    time.sleep(DELAY)
