"""Narrow live patch: report chat activity to the embedding BZBGEAR tab manager."""

import subprocess
from pathlib import Path


REMOTE = r"""from datetime import datetime, timezone
from pathlib import Path

path = Path('/opt/assistant/chat.html')
source = path.read_text()
old = '''function updateParentTitle(text) {
  if (window.parent === window || _titleContext.length >= 3) return;'''
new = '''function advisorParentOrigin() {
  try {
    const origin = new URL(document.referrer).origin;
    return ['https://bzbgear.com', 'https://dev.bzbgear.com'].includes(origin) ? origin : null;
  } catch (_) { return null; }
}

function notifyParentActivity() {
  const origin = advisorParentOrigin();
  if (window.parent !== window && origin) window.parent.postMessage({ type: 'bzb-advisor-activity' }, origin);
}

function updateParentTitle(text) {
  if (window.parent === window || _titleContext.length >= 3) return;'''
if source.count(old) != 1 or source.count("'https://dev.bzbgear.com');") != 2:
    raise SystemExit('Live bridge structure changed; refusing patch')
source = source.replace(old, new)
source = source.replace("'https://dev.bzbgear.com');", "advisorParentOrigin() || 'https://dev.bzbgear.com');")
old_activity = "if (role === 'user') updateParentTitle(text);"
if source.count(old_activity) != 1:
    raise SystemExit('Chat activity hook changed; refusing patch')
source = source.replace(old_activity, "if (role === 'user') { notifyParentActivity(); updateParentTitle(text); }")
backup = path.with_name(path.name + '.bak-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-tab-activity')
backup.write_text(path.read_text())
path.write_text(source)
print('Patched chat bridge; backup', backup)
"""


cmd = ["ssh", "-F", str(Path.home() / ".ssh" / "bzb_ovh_config"),
       "-o", "BatchMode=yes", "bzb-web01", "sudo", "-n", "python3", "-"]
subprocess.run(cmd, input=REMOTE.encode(), check=True)
