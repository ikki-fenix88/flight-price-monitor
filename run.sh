#!/usr/bin/env bash
# Wrapper para rodar via cron carregando as variáveis do .env.
# Uso no crontab:
#   0 9,22 * * * /home/usuario/flight-price-monitor/run.sh
cd "$(dirname "$0")" || exit 1
set -a
[ -f .env ] && . ./.env
set +a
python3 -u monitor.py >> monitor_log.txt 2>&1
