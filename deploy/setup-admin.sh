#!/usr/bin/env bash
set -euo pipefail

env_file=/opt/assistant/.env
if ! grep -q '^ADVISOR_ADMIN_PASSWORD=' "$env_file"; then
    umask 077
    printf 'ADVISOR_ADMIN_PASSWORD=%s\n' "$(openssl rand -hex 24)" >> "$env_file"
fi
chown advisor:advisor "$env_file"
chmod 600 "$env_file"
