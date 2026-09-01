#!/bin/sh
# Prefer MYSQL_* from env_file over compose-time DATABASE_URL defaults.
if [ -n "${MYSQL_USER:-}" ] && [ -n "${MYSQL_PASSWORD:-}" ]; then
  export DATABASE_URL="mysql+pymysql://${MYSQL_USER}:${MYSQL_PASSWORD}@${MYSQL_HOST:-mysql}:3306/${MYSQL_DATABASE:-ai_tp}?charset=utf8mb4"
fi
