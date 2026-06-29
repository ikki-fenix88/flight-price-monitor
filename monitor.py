"""
Flight Price Monitor — busca passagens ida+volta no Google Flights e
alerta no Telegram quando o preço entra na faixa configurada.

Segredos (token e chat IDs) vêm de variáveis de ambiente — veja .env.example.
Configuração das rotas/preços fica no dicionário ROTAS abaixo.

Licença: MIT. Uso pessoal. Veja avisos no README.
"""

import os
import re
import time
import base64
import requests
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By

# ─── SEGREDOS (via variáveis de ambiente) ─────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_IDS = [
    c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()
]

# ─── CONFIGURAÇÃO DAS ROTAS ───────────────────────────────────
# Cada rota é independente. Copie/edite os blocos como quiser.
#   dia_ida: weekday da ida (0=seg, 1=ter, 2=qua, 3=qui, 4=sex, 5=sab, 6=dom)
#   dia_volta_offset: nº de dias depois da ida em que é a volta
#   bidirecional: True busca SP->destino E destino->SP
ROTAS = [
    {
        "nome": "SP <-> LDB (Londrina)",
        "aeroportos_sp": ["CGH", "GRU", "VCP"],
        "destino": "LDB",
        "dia_ida": 5,            # sábado
        "dia_volta_offset": 2,   # volta na segunda
        "nome_ida": "sábado",
        "nome_volta": "segunda",
        "preco_min": 250,
        "preco_max": 450,
        "bidirecional": True,
    },
    {
        "nome": "SP <-> UDI (Uberlândia)",
        "aeroportos_sp": ["CGH", "GRU", "VCP"],
        "destino": "UDI",
        "dia_ida": 4,            # sexta
        "dia_volta_offset": 2,   # volta no domingo
        "nome_ida": "sexta",
        "nome_volta": "domingo",
        "preco_min": 250,
        "preco_max": 450,
        "bidirecional": True,
    },
]

SEMANAS_A_FRENTE = 40            # quantas semanas à frente monitorar
SEGUNDOS_RENDER = 22             # espera o JS do Google Flights renderizar
LIMITE_TELEGRAM = 4000           # Telegram corta mensagens acima de ~4096

# Nomes amigáveis para exibição (opcional)
NOMES_AEROPORTOS = {
    "CGH": "Congonhas",
    "GRU": "Guarulhos",
    "VCP": "Viracopos",
}
# ──────────────────────────────────────────────────────────────


def gerar_datas(dia_ida, dia_volta_offset, semanas=SEMANAS_A_FRENTE):
    """Gera pares (data_ida, data_volta) para as próximas N semanas."""
    hoje = datetime.today()
    resultado = []
    for i in range(semanas * 7):
        d = hoje + timedelta(days=i + 1)
        if d.weekday() == dia_ida:
            volta = d + timedelta(days=dia_volta_offset)
            resultado.append((d.strftime("%Y-%m-%d"), volta.strftime("%Y-%m-%d")))
    return resultado


def abrir_driver():
    """Inicia o Chrome headless. O Selenium Manager (>=4.6) baixa o driver sozinho."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--disable-extensions")
    options.add_argument("--no-first-run")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # Se o Chrome estiver num caminho não-padrão, descomente e ajuste:
    # options.binary_location = "/usr/bin/google-chrome-stable"
    return webdriver.Chrome(options=options)


def montar_url_tfs(origem, destino, data_ida, data_volta):
    """
    Monta a URL direta do Google Flights.
    O parâmetro `tfs` é um payload protobuf (engenharia reversa) codificado
    em base64. Funciona para qualquer par de aeroportos IATA de 3 letras.
    ⚠️ Pode quebrar se o Google mudar esse formato interno.
    """
    p1 = bytes([0x08, 0x1C, 0x10, 0x02, 0x1A, 0x1E, 0x12, 0x0A]) + data_ida.encode()
    p2 = bytes([0x6A, 0x07, 0x08, 0x01, 0x12, 0x03]) + origem.encode()
    p3 = bytes([0x72, 0x07, 0x08, 0x01, 0x12, 0x03]) + destino.encode()
    p4 = bytes([0x1A, 0x1E, 0x12, 0x0A]) + data_volta.encode()
    p5 = bytes([0x6A, 0x07, 0x08, 0x01, 0x12, 0x03]) + destino.encode()
    p6 = bytes([0x72, 0x07, 0x08, 0x01, 0x12, 0x03]) + origem.encode()
    tfs = base64.b64encode(p1 + p2 + p3 + p4 + p5 + p6).decode().rstrip("=")
    return f"https://www.google.com/travel/flights?hl=pt-BR&curr=BRL&tfs={tfs}"


def extrair_preco(driver, origem, destino, data_ida, data_volta):
    """Abre o Google Flights e extrai o menor preço ida+volta encontrado."""
    url = montar_url_tfs(origem, destino, data_ida, data_volta)
    try:
        driver.get(url)
        time.sleep(SEGUNDOS_RENDER)
        body = driver.find_element(By.TAG_NAME, "body").text
        linhas = body.split("\n")
        precos = []
        for i, linha in enumerate(linhas):
            if linha.strip() == "ida e volta" and i > 0:
                for m in re.findall(r"R\$\s*([\d\.]+)", linhas[i - 1].strip()):
                    v = float(m.replace(".", ""))
                    if 100 < v < 50000:
                        precos.append(v)
        time.sleep(4)
        return min(precos) if precos else None
    except Exception as e:
        print(f"    Erro {origem}->{destino}: {e}")
        return None


# ─── TELEGRAM ─────────────────────────────────────────────────
def dividir_mensagem(texto, limite=LIMITE_TELEGRAM):
    """Divide um texto longo em pedaços <= limite, quebrando em linhas."""
    pedacos, atual = [], ""
    for linha in texto.split("\n"):
        while len(linha) > limite:                # linha isolada gigante
            if atual:
                pedacos.append(atual)
                atual = ""
            pedacos.append(linha[:limite])
            linha = linha[limite:]
        if atual and len(atual) + 1 + len(linha) > limite:
            pedacos.append(atual)
            atual = linha
        else:
            atual = atual + ("\n" if atual else "") + linha
    if atual:
        pedacos.append(atual)
    return pedacos


def enviar_telegram(msg):
    """Envia msg para todos os chats, fatiando para respeitar o limite do Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_IDS:
        print("  [aviso] TELEGRAM_TOKEN/TELEGRAM_CHAT_IDS não configurados — pulando envio.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    pedacos = dividir_mensagem(msg)
    for chat_id in TELEGRAM_CHAT_IDS:
        for idx, pedaco in enumerate(pedacos, 1):
            try:
                r = requests.post(
                    url, data={"chat_id": chat_id, "text": pedaco}, timeout=10
                )
                if r.status_code == 200:
                    print(f"  Telegram {chat_id} parte {idx}/{len(pedacos)} enviada!")
                else:
                    print(f"  Erro Telegram {chat_id} parte {idx}: {r.text}")
                time.sleep(0.5)
            except Exception as e:
                print(f"  Falha Telegram {chat_id} parte {idx}: {e}")


# ─── PROCESSAMENTO ────────────────────────────────────────────
def processar_rota(driver, rota):
    """Processa uma rota completa e devolve (lista_de_alertas, driver)."""
    destino = rota["destino"]
    preco_min, preco_max = rota["preco_min"], rota["preco_max"]
    nome_ida, nome_volta = rota["nome_ida"], rota["nome_volta"]
    bidirecional = rota.get("bidirecional", False)

    datas = gerar_datas(rota["dia_ida"], rota["dia_volta_offset"])
    alertas = []

    print(f"\n{'─' * 58}")
    print(f"  ROTA: {rota['nome']}")
    print(f"  Faixa: R$ {preco_min}–{preco_max} | {nome_ida} a {nome_volta}")
    print(f"{'─' * 58}\n")

    for data_ida, data_volta in datas:
        print(f"  {nome_ida} {data_ida} / {nome_volta} {data_volta}")

        # Reinicia o driver se ele tiver morrido
        try:
            driver.title
        except Exception:
            print("    Reiniciando driver...")
            try:
                driver.quit()
            except Exception:
                pass
            driver = abrir_driver()

        for sentido in (("SP", destino),) + ((( destino, "SP"),) if bidirecional else ()):
            ida_sp = sentido[0] == "SP"
            print(f"    --- {sentido[0]} -> {sentido[1]} ---")
            melhor_p, melhor_a = None, None
            for sp in rota["aeroportos_sp"]:
                origem = sp if ida_sp else destino
                dest = destino if ida_sp else sp
                print(f"      {origem} -> {dest}...", end=" ")
                preco = extrair_preco(driver, origem, dest, data_ida, data_volta)
                if preco:
                    print(f"R$ {preco:.0f}")
                    if melhor_p is None or preco < melhor_p:
                        melhor_p, melhor_a = preco, sp
                else:
                    print("nao encontrado")

            if melhor_p and preco_min <= melhor_p <= preco_max:
                nome_aero = NOMES_AEROPORTOS.get(melhor_a, melhor_a)
                if ida_sp:
                    link = montar_url_tfs(melhor_a, destino, data_ida, data_volta)
                    alertas.append(
                        f"SP -> {destino}\n"
                        f"Ida: {nome_ida} {data_ida}  {melhor_a} ({nome_aero}) -> {destino}\n"
                        f"Volta: {nome_volta} {data_volta}  {destino} -> {melhor_a} ({nome_aero})\n"
                        f"Total: R$ {melhor_p:.0f}\n{link}"
                    )
                else:
                    link = montar_url_tfs(destino, melhor_a, data_ida, data_volta)
                    alertas.append(
                        f"{destino} -> SP\n"
                        f"Ida: {nome_ida} {data_ida}  {destino} -> {melhor_a} ({nome_aero})\n"
                        f"Volta: {nome_volta} {data_volta}  {melhor_a} ({nome_aero}) -> {destino}\n"
                        f"Total: R$ {melhor_p:.0f}\n{link}"
                    )
        print()

    return alertas, driver


def main():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'=' * 58}\n  Monitor de Voos  |  {agora}\n"
          f"  {len(ROTAS)} rota(s) | {SEMANAS_A_FRENTE} semanas\n{'=' * 58}")

    driver = abrir_driver()
    resultados = []
    try:
        for rota in ROTAS:
            alertas, driver = processar_rota(driver, rota)
            resultados.append((rota, alertas))
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print(f"\n{'=' * 58}\nEnviando resultados no Telegram...")
    for rota, alertas in resultados:
        cab = (f"🔔 Monitor de Voos | {agora}\n{'═' * 30}\n\n"
               f"✈️ {rota['nome']}\n"
               f"📅 {rota['nome_ida']} a {rota['nome_volta']}\n"
               f"💰 Faixa: R$ {rota['preco_min']}–{rota['preco_max']}\n")
        if alertas:
            corpo = f"✅ {len(alertas)} passagem(ns) encontrada(s):\n\n"
            for a in alertas:
                corpo += f"----\n{a}\n\n"
        else:
            corpo = (f"❌ Nenhuma passagem na faixa nas próximas "
                     f"{SEMANAS_A_FRENTE} semanas.\n")
        # Cada rota é enviada separadamente: falha numa não derruba a outra.
        enviar_telegram(cab + corpo)

    print(f"{'=' * 58}\n")


if __name__ == "__main__":
    main()
