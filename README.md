# ✈️ Flight Price Monitor

Monitor automático de passagens aéreas **ida + volta**. Busca preços no Google Flights para as rotas que você configurar, e te avisa no **Telegram** quando alguma passagem entra na faixa de preço desejada. Roda sozinho num servidor barato (ou de graça), 2x por dia.

Feito para quem viaja sempre nas mesmas rotas (ex.: voltar pra casa no fim de semana) e quer ser avisado quando aparecer passagem boa — sem ficar olhando preço todo dia.

---

## 📑 Índice

- [Como funciona](#-como-funciona)
- [Recursos](#-recursos)
- [Exemplo de alerta](#-exemplo-de-alerta)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação](#-instalação)
- [Configuração](#-configuração)
- [Como rodar](#-como-rodar)
- [Agendar (rodar sozinho)](#-agendar-rodar-sozinho)
- [Estrutura do projeto](#-estrutura-do-projeto)
- [Como funciona por dentro](#-como-funciona-por-dentro)
- [Solução de problemas](#-solução-de-problemas)
- [Limitações e avisos](#-limitações-e-avisos)
- [Roadmap](#-roadmap)
- [Licença](#-licença)

---

## 🔎 Como funciona

```
┌─────────────┐    2x/dia     ┌──────────────┐   abre via    ┌────────────────┐
│  Agendador  │ ────────────▶ │  monitor.py  │ ────────────▶ │ Google Flights │
│   (cron)    │               │  (Selenium)  │   navegador   │  (headless)    │
└─────────────┘               └──────┬───────┘               └────────────────┘
                                     │ preço dentro da faixa?
                                     ▼
                              ┌──────────────┐
                              │   Telegram   │  →  alerta para 1+ pessoas
                              └──────────────┘
```

Para cada rota configurada, o script:

1. Gera as datas dos próximos *N* fins de semana (com base no dia da ida e na duração).
2. Abre o Google Flights (Chrome headless) para cada combinação de aeroporto e data.
3. Lê o menor preço ida+volta da página.
4. Se o preço estiver dentro da faixa `[mín, máx]`, monta um alerta com o link direto da busca.
5. Envia tudo no Telegram, fatiando a mensagem se ela for grande.

---

## ✨ Recursos

- **Múltiplas rotas** independentes, cada uma com sua própria faixa de preço e dias de viagem.
- **Busca bidirecional** (ida saindo da origem *ou* do destino) e em **vários aeroportos** de uma mesma cidade.
- **Alertas no Telegram** para um ou vários destinatários.
- **Mensagens longas fatiadas** automaticamente (respeita o limite de 4096 caracteres do Telegram — sem perder alertas).
- **Link direto** do Google Flights em cada alerta.
- **Segredos fora do código** (token e chat IDs em variáveis de ambiente).
- **Roda em VM gratuita** (testado em Oracle Cloud Free Tier, 1 vCPU / 1 GB RAM, Ubuntu).

---

## 💬 Exemplo de alerta

```
🔔 Monitor de Voos | 14/06/2026 06:00
══════════════════════════════

✈️ SP <-> LDB (Londrina)
📅 sábado a segunda
💰 Faixa: R$ 250–450
✅ 2 passagem(ns) encontrada(s):

----
SP -> LDB
Ida: sábado 2026-07-11  CGH (Congonhas) -> LDB
Volta: segunda 2026-07-13  LDB -> CGH (Congonhas)
Total: R$ 388
https://www.google.com/travel/flights?...
```

---

## ✅ Pré-requisitos

- **Python 3.9+**
- **Google Chrome** (ou Chromium) instalado na máquina/servidor.
- Uma conta no **Telegram** (para criar o bot).
- Um lugar para rodar 24/7: um servidor, uma VM na nuvem (Oracle Cloud, AWS, etc.) ou até um Raspberry Pi. Não precisa ficar no seu PC.

> O Selenium 4.6+ baixa o ChromeDriver automaticamente (Selenium Manager) — você só precisa ter o Chrome instalado.

---

## 🚀 Instalação

### 1. Clonar e instalar dependências

```bash
git clone https://github.com/marlondenez-hub/flight-price-monitor.git
cd flight-price-monitor
pip install -r requirements.txt
```

### 2. Instalar o Chrome (no servidor Linux)

```bash
# Ubuntu/Debian
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
```

### 3. Criar o bot do Telegram e pegar o token

1. No Telegram, fale com o **@BotFather**.
2. Envie `/newbot` e siga as instruções (nome + @username do bot).
3. O BotFather devolve um **token** (algo como `123456789:AAE...`). Guarde.

### 4. Descobrir o seu chat ID

1. Mande qualquer mensagem para o **seu novo bot** (procure pelo @username dele).
2. Acesse no navegador: `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
3. Procure por `"chat":{"id":...}` — esse número é o seu **chat ID**.
4. Para alertar mais de uma pessoa, cada uma faz o mesmo e você junta os IDs separados por vírgula.

### 5. Configurar os segredos

```bash
cp .env.example .env
nano .env   # preencha TELEGRAM_TOKEN e TELEGRAM_CHAT_IDS
```

---

## ⚙️ Configuração

As rotas ficam no dicionário **`ROTAS`**, no topo do `monitor.py`. Cada bloco é uma rota:

```python
{
    "nome": "SP <-> LDB (Londrina)",       # rótulo exibido no alerta
    "aeroportos_sp": ["CGH", "GRU", "VCP"], # aeroportos da cidade de origem
    "destino": "LDB",                       # código IATA do destino
    "dia_ida": 5,            # 0=seg, 1=ter, 2=qua, 3=qui, 4=sex, 5=sab, 6=dom
    "dia_volta_offset": 2,   # nº de dias depois da ida (sáb + 2 = seg)
    "nome_ida": "sábado",
    "nome_volta": "segunda",
    "preco_min": 250,        # ignora preços abaixo disso
    "preco_max": 450,        # ignora preços acima disso
    "bidirecional": True,    # busca origem->destino E destino->origem
}
```

Outras constantes ajustáveis:

| Constante | O que faz |
|---|---|
| `SEMANAS_A_FRENTE` | Quantas semanas à frente monitorar (padrão 40). |
| `SEGUNDOS_RENDER` | Espera o JS do Google carregar (aumente se a rede for lenta). |
| `NOMES_AEROPORTOS` | Mapa código → nome amigável (opcional). |

> 💡 Os códigos são **IATA de 3 letras** (GRU, CGH, LDB, GIG, BSB...). Funciona para qualquer aeroporto.

---

## ▶️ Como rodar

Teste manual (com os segredos carregados):

```bash
# Linux/Mac — carrega o .env e roda
set -a; . ./.env; set +a
python3 -u monitor.py
```

A primeira rodada completa demora bastante (ver [Limitações](#-limitações-e-avisos)). Para um teste rápido, reduza `SEMANAS_A_FRENTE` para 2 ou 3 temporariamente.

---

## ⏰ Agendar (rodar sozinho)

Use o `run.sh` incluído (ele carrega o `.env` e grava o log):

```bash
chmod +x run.sh
crontab -e
```

Adicione (exemplo: 06h e 19h todo dia):

```
0 9  * * * /home/usuario/flight-price-monitor/run.sh
0 22 * * * /home/usuario/flight-price-monitor/run.sh
```

> ⚠️ O cron usa **UTC** por padrão em muitos servidores. No exemplo, `9` e `22` UTC = `06h` e `19h` em Brasília (UTC−3). Ajuste ao seu fuso.

---

## 📁 Estrutura do projeto

```
flight-price-monitor/
├── monitor.py          # script principal
├── run.sh              # wrapper para o cron (carrega .env + grava log)
├── requirements.txt    # dependências Python
├── .env.example        # modelo de configuração de segredos
├── .gitignore          # ignora .env, chaves e logs
└── README.md           # este arquivo
```

---

## 🛠️ Como funciona por dentro

**Link direto do Google Flights.** Em vez de preencher formulário, o script monta a URL final usando o parâmetro `tfs` — um payload binário (protobuf) codificado em base64 que descreve origem, destino e datas. Isso pula a interface e vai direto ao resultado. A função `montar_url_tfs()` monta esse payload para qualquer par de aeroportos.

**Leitura do preço.** A página é renderizada via Selenium (Chrome headless); o script lê o texto do `body`, procura a âncora `"ida e volta"` e captura o valor `R$ ...` imediatamente acima. Pega o menor preço válido.

**Telegram robusto.** O Telegram rejeita mensagens com mais de ~4096 caracteres. A função `dividir_mensagem()` quebra qualquer texto em pedaços ≤4000, sempre cortando em quebras de linha (nunca no meio de um voo). Cada rota é enviada **separadamente**, então um problema numa rota nunca impede o envio da outra.

> 🐞 *Nota de quem construiu:* a falha mais traiçoeira aqui foi exatamente o limite do Telegram — uma rota que achava **muitas** passagens gerava uma mensagem grande demais e era **descartada inteira** pela API, dando a impressão de que aquela rota "não funcionava". O fatiamento por linha resolve isso.

---

## 🩺 Solução de problemas

| Sintoma | Causa provável | Solução |
|---|---|---|
| `Bad Request: message is too long` | Mensagem > 4096 caracteres | Já tratado por `dividir_mensagem()`. Não baixe o `LIMITE_TELEGRAM`. |
| Chrome "exited abnormally" / crash | Pouca RAM no servidor | Adicione swap (1 GB resolve em VMs de 1 GB). |
| Nenhuma passagem encontrada nunca | Faixa de preço apertada demais | Aumente o `preco_max`. |
| Preços vindo errados / vazios | Google mudou o layout | Aumente `SEGUNDOS_RENDER`; revise o parsing em `extrair_preco()`. |
| `[aviso] TELEGRAM_TOKEN... não configurados` | `.env` não carregado | Garanta que o `run.sh`/seu shell carregou o `.env`. |
| Aviso `RequestsDependencyWarning: urllib3...` | Versões de libs | Cosmético, pode ignorar. |

### Adicionar swap num servidor de 1 GB (Linux)

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## ⚠️ Limitações e avisos

- **Velocidade.** Cada busca leva ~26s (espera o JS renderizar). Muitas rotas × aeroportos × semanas pode levar **horas** por rodada. Comece pequeno e ajuste `SEMANAS_A_FRENTE`.
- **Fragilidade.** Depende do HTML e do parâmetro `tfs` do Google Flights, que **podem mudar sem aviso** e quebrar a leitura. É a natureza de qualquer scraping.
- **Uso pessoal.** Este projeto faz scraping do Google Flights para uso pessoal e em baixo volume. Automatizar acesso a sites pode contrariar os Termos de Serviço deles — use com bom senso, sem volume agressivo, e por sua conta e risco.
- **Sem garantia de preço.** Os valores são os exibidos no momento da busca; o preço final é sempre o do site da companhia/agência.

---

## 🗺️ Roadmap

Ideias de evolução (contribuições bem-vindas):

- [ ] Histórico de preços (CSV/SQLite) + gráfico de evolução.
- [ ] Notificação por outros canais (e-mail, WhatsApp).
- [ ] Trocar Selenium por uma API de voos (mais rápido e estável).
- [ ] Dockerfile para subir em qualquer lugar com um comando.
- [ ] Testes automatizados do parser e do fatiador de mensagens.

---

## 📄 Licença

[MIT](LICENSE) — use, modifique e compartilhe livremente. Sem garantias.

---

> Feito para resolver um problema real: parar de checar preço de passagem na mão. Se te ajudou, deixa uma ⭐ e compartilha com quem voa sempre nas mesmas rotas.
