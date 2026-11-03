"""Verify that the new Advisor's protected admin endpoints work locally."""
import base64
import json
from pathlib import Path
from urllib.request import Request, urlopen

from dotenv import dotenv_values


password = dotenv_values(Path(__file__).resolve().parents[1] / ".env")["ADVISOR_ADMIN_PASSWORD"]
assert password and len(password) >= 24
auth = base64.b64encode(f"admin:{password}".encode()).decode()
for path in ("/admin", "/admin/sessions?limit=1", "/debug/annotations"):
    req = Request("http://127.0.0.1:8001" + path, headers={"Authorization": "Basic " + auth})
    with urlopen(req, timeout=15) as response:
        payload = response.read()
        print(path, response.status, len(payload))
        if path.startswith("/admin/sessions"):
            assert isinstance(json.loads(payload), list)
