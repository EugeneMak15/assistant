"""Dry-run or switch the previous VPS into a verified HTTPS forwarder.

This keeps visitors with cached old DNS on the new Advisor and removes the
old site-wide browser password. The new Advisor protects /admin itself.
"""

import argparse
import getpass
import os
from pathlib import Path

import paramiko


REMOTE = r'''import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
base = Path("/etc/nginx/fastpanel2-sites/xlink_one_bz_usr")
conf = base / "assistant.bzbgear.com.conf"
includes = base / "assistant.bzbgear.com.includes"
original = conf.read_text()
auth = includes.read_text()
old = "proxy_pass http://assistant.bzbgear.com9;"
if original.count(old) != 2 or 'auth_basic "BZB Advisor";' not in auth:
    raise SystemExit("Old VPS Nginx config changed; refusing cutover")
ca = Path("/etc/pki/tls/certs/ca-bundle.crt")
if not ca.is_file():
    raise SystemExit("CA bundle missing")
new = """proxy_pass https://15.204.65.182;
        proxy_ssl_server_name on;
        proxy_ssl_name assistant.bzbgear.com;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate /etc/pki/tls/certs/ca-bundle.crt;
        proxy_ssl_verify_depth 3;
        proxy_buffering off;
        proxy_read_timeout 180s;"""
modified = original.replace(old, new)
print("Verified two proxy locations and site-wide Basic Auth include")
if not args.apply:
    print("Dry run only; old VPS unchanged")
    raise SystemExit(0)
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
conf_backup = conf.with_name(conf.name + ".advisor-backup-" + stamp)
auth_backup = includes.with_name(includes.name + ".advisor-backup-" + stamp)
shutil.copy2(conf, conf_backup)
shutil.copy2(includes, auth_backup)
try:
    temp = conf.with_name(conf.name + ".advisor-tmp")
    temp.write_text(modified)
    os.chmod(temp, conf.stat().st_mode)
    os.chown(temp, conf.stat().st_uid, conf.stat().st_gid)
    os.replace(temp, conf)
    includes.write_text("# Public Advisor; /admin authentication is enforced by the app.\n")
    subprocess.run(["nginx", "-t"], check=True)
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
except Exception:
    shutil.copy2(conf_backup, conf)
    shutil.copy2(auth_backup, includes)
    subprocess.run(["nginx", "-t"], check=False)
    subprocess.run(["systemctl", "reload", "nginx"], check=False)
    raise
print("Old VPS now forwards to new VPS; backups:", conf_backup, auth_backup)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("ADVISOR_SOURCE_PASSWORD") or getpass.getpass("Current Advisor root SSH password: ")
    client = paramiko.SSHClient()
    client.load_host_keys(str(Path.home() / ".ssh" / "known_hosts"))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect("209.159.152.124", username="root", password=password,
                   timeout=20, look_for_keys=False, allow_agent=False)
    try:
        sftp = client.open_sftp()
        with sftp.open("/tmp/advisor_old_vps_forward.py", "w") as remote:
            remote.write(REMOTE.encode())
        sftp.close()
        mode = "--apply" if args.apply else ""
        _, stdout, stderr = client.exec_command(f"/opt/assistant/venv/bin/python /tmp/advisor_old_vps_forward.py {mode}", timeout=60)
        print(stdout.read().decode(errors="replace"))
        error = stderr.read().decode(errors="replace")
        status = stdout.channel.recv_exit_status()
        if status:
            raise RuntimeError(f"Cutover failed ({status}): {error}")
    finally:
        client.exec_command("rm -f /tmp/advisor_old_vps_forward.py")
        client.close()


if __name__ == "__main__":
    main()
