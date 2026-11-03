#!/usr/bin/env bash
set -euo pipefail

expected_sha=${1:?GitHub commit SHA required}
if [[ ! "$expected_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid commit SHA" >&2
  exit 2
fi

cd /opt/assistant
sudo -u advisor git fetch --quiet origin main:refs/remotes/origin/main
actual_sha=$(sudo -u advisor git rev-parse origin/main)
if [[ "$actual_sha" != "$expected_sha" ]]; then
  echo "Remote main is not the workflow commit; refusing stale deploy" >&2
  exit 1
fi
sudo -u advisor git switch main
sudo -u advisor git merge --ff-only origin/main
sudo -u advisor /opt/assistant/venv/bin/pip install -q -r requirements.txt
systemctl restart bzb-advisor.service
for attempt in {1..20}; do
  if curl --fail --silent --show-error http://127.0.0.1:8001/health >/dev/null 2>&1; then
    echo "Advisor deployed: $expected_sha"
    exit 0
  fi
  sleep 2
done
systemctl status bzb-advisor.service --no-pager -l >&2
exit 1
