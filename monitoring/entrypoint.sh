#!/bin/sh
# Генерирует /tmp/prometheus.yml из шаблона, подставляя METRICS_AUTH_TOKEN
# из окружения. Если токен пуст — режет блок authorization целиком.
set -e

TMPL=/etc/prometheus/prometheus.yml.tmpl
OUT=/tmp/prometheus.yml

if [ -z "${METRICS_AUTH_TOKEN:-}" ]; then
  # Вырезаем 3 строки блока authorization (с отступом 4 пробела)
  sed '/^    authorization:$/,/^      credentials: /d' "$TMPL" > "$OUT"
else
  # Подставляем токен. Используем | как разделитель — токен может содержать /
  sed "s|__METRICS_AUTH_TOKEN__|${METRICS_AUTH_TOKEN}|g" "$TMPL" > "$OUT"
fi

exec /bin/prometheus \
  --config.file="$OUT" \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time="${PROMETHEUS_RETENTION:-30d}" \
  --web.console.libraries=/usr/share/prometheus/console_libraries \
  --web.console.templates=/usr/share/prometheus/consoles \
  --web.enable-lifecycle
