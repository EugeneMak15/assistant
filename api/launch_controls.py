"""Public request quota, administrator authentication, and operational alerts."""
import base64
import hmac
import ipaddress
import logging
import os
import smtplib
import threading
from contextlib import closing
from datetime import datetime, timezone
from email.message import EmailMessage

from .db import get_conn

LOG = logging.getLogger(__name__)
ALERT_TO = "eugene.m@bzbgear.com"


def init_launch_tables():
    with closing(get_conn()) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS daily_ip_requests (day TEXT NOT NULL, ip TEXT NOT NULL, count INTEGER NOT NULL, PRIMARY KEY(day, ip))")
        db.execute("CREATE TABLE IF NOT EXISTS launch_alerts (day TEXT NOT NULL, kind TEXT NOT NULL, subject TEXT NOT NULL, sent_at TEXT, PRIMARY KEY(day, kind, subject))")


def _send_alert(subject, body):
    host = os.getenv("ALERT_SMTP_HOST")
    sender = os.getenv("ALERT_SMTP_FROM")
    if not host or not sender:
        LOG.error("Alert email not configured: %s", subject)
        return False
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ALERT_TO
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        port = int(os.getenv("ALERT_SMTP_PORT", "587"))
        client = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with client(host, port, timeout=15) as smtp:
            if port != 465:
                smtp.starttls()
            smtp.login(os.environ["ALERT_SMTP_USER"], os.environ["ALERT_SMTP_PASSWORD"])
            smtp.send_message(msg)
        return True
    except Exception:
        LOG.exception("Could not send launch alert")
        return False


def alert_once(day, kind, subject, title, body):
    with closing(get_conn()) as db, db:
        row = db.execute("SELECT sent_at FROM launch_alerts WHERE day=? AND kind=? AND subject=?", (day, kind, subject)).fetchone()
        if row:
            return
        db.execute("INSERT INTO launch_alerts(day,kind,subject) VALUES (?,?,?)", (day, kind, subject))

    def deliver():
        ok = _send_alert(title, body)
        if ok:
            with closing(get_conn()) as db, db:
                db.execute("UPDATE launch_alerts SET sent_at=datetime('now') WHERE day=? AND kind=? AND subject=?", (day, kind, subject))
        else:
            with closing(get_conn()) as db, db:
                db.execute("DELETE FROM launch_alerts WHERE day=? AND kind=? AND subject=? AND sent_at IS NULL", (day, kind, subject))

    threading.Thread(target=deliver, daemon=True).start()


def is_admin(request) -> bool:
    expected_user = os.getenv("ADVISOR_ADMIN_USERNAME", "admin")
    expected = os.getenv("ADVISOR_ADMIN_PASSWORD", "")
    header = request.headers.get("authorization", "")
    if not expected or not header.lower().startswith("basic "):
        return False
    try:
        user, password = base64.b64decode(header[6:], validate=True).decode().split(":", 1)
    except (ValueError, UnicodeError):
        return False
    return hmac.compare_digest(user, expected_user) and hmac.compare_digest(password, expected)


def admin_challenge():
    from fastapi.responses import Response
    return Response("Administrator sign-in required", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="BZB Advisor Admin"', "Cache-Control": "no-store"})


def client_ip(request) -> str:
    peer = request.client.host if request.client else "unknown"
    # Only trust Nginx's address header when the direct peer is the local proxy.
    if peer in ("127.0.0.1", "::1"):
        real = request.headers.get("x-real-ip", "").strip()
        try:
            return str(ipaddress.ip_address(real))
        except ValueError:
            pass
    return peer


def enforce_daily_limit(request):
    from fastapi.responses import JSONResponse
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ip = client_ip(request)
    count = count_request(day, ip)
    if count > 100:
        alert_once(day, "ip_limit", ip, f"Advisor: over 100 requests from {ip}",
                   f"IP: {ip}\nUTC day: {day}\nAttempts: {count}\nPublic API limit: 100 chat starts, messages, recommendation streams or diagrams/day/IP.")
        return JSONResponse({"detail": "Daily request limit reached. Please try again tomorrow."}, status_code=429)
    return None


def count_request(day, ip):
    with closing(get_conn()) as db, db:
        db.execute("INSERT INTO daily_ip_requests(day,ip,count) VALUES (?,?,1) ON CONFLICT(day,ip) DO UPDATE SET count=count+1", (day, ip))
        count = db.execute("SELECT count FROM daily_ip_requests WHERE day=? AND ip=?", (day, ip)).fetchone()[0]
    return count


def check_daily_budget():
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with closing(get_conn()) as db, db:
        row = db.execute("SELECT COALESCE(SUM(estimated_cost_usd),0), SUM(estimated_cost_usd IS NULL) FROM chat_usage WHERE created_at >= unixepoch(?) AND created_at < unixepoch(?, '+1 day')", (day, day)).fetchone()
    cost, unpriced = row[0], row[1] or 0
    if cost > 10:
        alert_once(day, "budget", "all", "Advisor: estimated daily API cost exceeds $10",
                   f"UTC day: {day}\nEstimated cost: ${cost:.4f}\nUnpriced API calls: {unpriced}\nThis is a token-based estimate, not an invoice.")
