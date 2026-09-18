#!/usr/bin/with-contenv bashio
set -e

options_file="/data/options.json"
host="$(bashio::config 'comfoair_host')"
port="$(bashio::config 'comfoair_port')"
topic="$(bashio::config 'mqtt_base_topic')"
log_level="$(bashio::config 'log_level')"

if bashio::var.is_empty "${host}"; then
    bashio::log.error "ComfoAir host is not configured"
    exit 1
fi

mqtt_service="$(bashio::services mqtt)"
export MQTT_HOST="$(echo "${mqtt_service}" | jq -r '.host')"
export MQTT_PORT="$(echo "${mqtt_service}" | jq -r '.port')"
export MQTT_USER="$(echo "${mqtt_service}" | jq -r '.username // empty')"
export MQTT_PASSWORD="$(echo "${mqtt_service}" | jq -r '.password // empty')"

bashio::log.info "Starting ComfoAir MQTT Bridge"
exec python3 /app.py \
    --host "${host}" \
    --port "${port}" \
    --topic "${topic}" \
    --log-level "${log_level}" \
    --options-file "${options_file}"
