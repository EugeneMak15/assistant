"""Copy a consistent production Advisor snapshot to bzb-web01 over two SSH links.

The original service remains running. Use --final-merge after routing old-VPS
traffic to the new VPS; it preserves conversations created on both servers.
No password is stored.
"""

import argparse
import getpass
import os
import subprocess
import sys

import paramiko


OLD_HOST = "209.159.152.124"
OLD_KNOWN_HOSTS = r"C:\Users\eugen\.ssh\known_hosts"
NEW_SSH_CONFIG = r"C:\Users\eugen\.ssh\bzb_ovh_config"
CERT_BASENAME = "assistant.bzbgear.com_2026-06-24-11-07_06"


def remote_command(client, command):
    _, stdout, stderr = client.exec_command(command, timeout=120)
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"Old server command failed ({status}): {stderr.read().decode(errors='replace')}")


def pipe_archive(client, source_command, target_command):
    _, stdout, stderr = client.exec_command(source_command, timeout=1200)
    target = subprocess.Popen(
        ["ssh", "-F", NEW_SSH_CONFIG, "-o", "BatchMode=yes", "bzb-web01", target_command],
        stdin=subprocess.PIPE,
    )
    copied = 0
    try:
        while chunk := stdout.read(262144):
            target.stdin.write(chunk)
            copied += len(chunk)
        target.stdin.close()
        old_status = stdout.channel.recv_exit_status()
        new_status = target.wait(timeout=1200)
        if old_status or new_status:
            raise RuntimeError(f"Transfer failed: source={old_status}, destination={new_status}, source error={stderr.read().decode(errors='replace')}")
    finally:
        if target.poll() is None:
            target.kill()
    print(f"Transferred {copied / 1048576:.1f} MiB", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-merge", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("ADVISOR_SOURCE_PASSWORD") or getpass.getpass("Current Advisor root SSH password: ")
    client = paramiko.SSHClient()
    client.load_host_keys(OLD_KNOWN_HOSTS)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(OLD_HOST, username="root", password=password, timeout=20,
                   look_for_keys=False, allow_agent=False)
    try:
        remote_command(client, "cd /opt/assistant && /opt/assistant/venv/bin/python -c 'import sqlite3; a=sqlite3.connect(\"products.db\"); b=sqlite3.connect(\"_migration_products.db\"); a.backup(b); b.close(); a.close()'")
        if args.final_merge:
            remote_command(client, "cd /opt/assistant && /opt/assistant/venv/bin/python -c 'import sqlite3; a=sqlite3.connect(\"debug_annotations.db\"); b=sqlite3.connect(\"_migration_annotations.db\"); a.backup(b); b.close(); a.close()'")
            pipe_archive(
                client,
                "cd /opt/assistant && tar -cf - _migration_products.db _migration_annotations.db",
                "sudo -n mkdir -p /opt/assistant/_migration_stage && sudo -n tar -xf - -C /opt/assistant/_migration_stage && sudo -n chown -R advisor:advisor /opt/assistant/_migration_stage && sudo -n -u advisor /opt/assistant/venv/bin/python /opt/assistant/deploy/merge_migration_db.py",
            )
            return
        pipe_archive(
            client,
            "cd /opt/assistant && tar -cf - _migration_products.db chroma_db debug_annotations.db .env",
            "! sudo -n grep -q '^ADVISOR_ADMIN_PASSWORD=' /opt/assistant/.env && sudo -n tar -xf - -C /opt/assistant && sudo -n mv /opt/assistant/_migration_products.db /opt/assistant/products.db && sudo -n chown advisor:advisor /opt/assistant/products.db /opt/assistant/debug_annotations.db /opt/assistant/.env && sudo -n chown -R advisor:advisor /opt/assistant/chroma_db && sudo -n chmod 600 /opt/assistant/.env",
        )
        pipe_archive(
            client,
            f"tar -cf - -C /var/www/httpd-cert {CERT_BASENAME}.crt {CERT_BASENAME}.key",
            "sudo -n mkdir -p /opt/assistant/tls && sudo -n tar -xf - -C /opt/assistant/tls && sudo -n chown root:root /opt/assistant/tls/* && sudo -n chmod 600 /opt/assistant/tls/*.key",
        )
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
