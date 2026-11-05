"""Keep TAA catalog display separate from a request to recommend TAA gear."""

import subprocess
from pathlib import Path


REMOTE = r"""from datetime import datetime, timezone
from pathlib import Path

path = Path('/opt/assistant/api/chat.py')
source = path.read_text()
old = '''if (re.search(r"\\btaa(?:[ -]compliant)?\\b", user_message, re.I)
            and re.search(r"\\b(?:all|catalog|list|show|products?|equipment|devices?)\\b", user_message, re.I)):'''
new = '''if (re.search(r"\\btaa(?:[ -]compliant)?\\b", user_message, re.I)
            and _is_catalog_browse_request(user_message)):'''
if source.count(old) != 1:
    raise SystemExit(f'Refusing TAA guard patch: found {source.count(old)} matches')
backup = path.with_name(path.name + '.bak-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-taa-browse-guard')
backup.write_text(source)
path.write_text(source.replace(old, new))
print('Patched TAA browse guard; backup', backup)
"""


cmd = ["ssh", "-F", str(Path.home() / ".ssh" / "bzb_ovh_config"),
       "-o", "BatchMode=yes", "bzb-web01", "sudo", "-n", "python3", "-"]
subprocess.run(cmd, input=REMOTE.encode(), check=True)
