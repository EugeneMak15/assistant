#!/usr/bin/env bash
set -euo pipefail

cd /opt/assistant
sudo -u advisor mkdir -p _backup_predeploy
sudo -u advisor /opt/assistant/venv/bin/python sync_catalog_feed.py --db products.db --apply --backup-dir _backup_predeploy
backup_name="_backup_predeploy/chroma-$(date -u +%Y%m%dT%H%M%SZ)"
sudo -u advisor cp -a chroma_db "$backup_name"
sudo -u advisor /opt/assistant/venv/bin/python ingest_products.py
systemctl restart bzb-advisor.service
for attempt in {1..20}; do
  if curl --fail --silent --show-error http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "Advisor catalog synced"
    exit 0
  fi
  sleep 2
done
systemctl status bzb-advisor.service --no-pager -l >&2
exit 1
