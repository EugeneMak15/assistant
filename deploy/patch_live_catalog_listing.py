"""Narrow live patch for catalog-browse intent without replacing other live edits."""

import subprocess
from pathlib import Path


REMOTE = r"""from datetime import datetime, timezone
from pathlib import Path

root = Path('/opt/assistant')
files = {
    'api/chat.py': (root / 'api/chat.py').read_text(),
    'main.py': (root / 'main.py').read_text(),
    'tests/test_advisor_rules.py': (root / 'tests/test_advisor_rules.py').read_text(),
}
changes = {
    'api/chat.py': [
        (
            '_SCOPE_REPLY = "I can help with AV equipment and setups. What equipment or connection do you need help with?"',
            '''_SCOPE_REPLY = "I can help with AV equipment and setups. What equipment or connection do you need help with?"


def _is_catalog_browse_request(message: str) -> bool:
    # A request to display products is not a request to choose a winner.
    if re.search(r"\\b(?:best|recommend|suggest|choose|pick|select|setup|system|solution)\\b", message, re.I):
        return False
    has_browse_verb = re.search(r"\\b(?:show|list|browse|display|see)\\b|покажи|перечисли|список", message, re.I)
    has_catalog_target = re.search(r"\\b(?:all|products?|models?|catalog|devices?|equipment|cameras?)\\b|все|товары|продукты|камеры", message, re.I)
    return bool(has_browse_verb and has_catalog_target)
''',
        ),
        (
            '"flow": "product_selection", "requested_categories": [],\n                "scenario_type": "other", "scenario_summary": user_message,',
            '"flow": "catalog_listing", "requested_categories": [],\n                "scenario_type": "other", "scenario_summary": user_message,',
        ),
        (
            '    # Build scenario plan from intent (used by SQL filter downstream)\n',
            '''    # Explicit browsing requests go directly to catalog results, without
    # clarifying questions or a best-product recommendation.
    if _is_catalog_browse_request(user_message):
        ready = True
        chips = []
        msg = "Here are the matching products in our catalog."
        sq = user_message
        intent["flow"] = "catalog_listing"

    # Build scenario plan from intent (used by SQL filter downstream)
''',
        ),
    ],
    'main.py': [
        (
            'if flow in ("product_selection", "hybrid"):\n            categories = scenario_plan.get("requested_categories", [])',
            'if flow in ("product_selection", "hybrid", "catalog_listing"):\n            categories = scenario_plan.get("requested_categories", [])',
        ),
        (
            '        if flow in ("product_selection", "hybrid"):\n            gen = stream_flow_a_recommendation(',
            '''        if flow == "catalog_listing":
            # Listing mode emits every eligible product and no LLM opinion.
            for sku in sql_skus:
                conn = get_conn()
                try:
                    row = conn.execute("SELECT * FROM products WHERE id=?", (sku,)).fetchone()
                finally:
                    conn.close()
                if not row:
                    continue
                product = Product(**row_to_dict(row))
                collected_skus.append(sku)
                yield f"data: {_json.dumps({'type': 'product', 'product': product.model_dump()})}\\n\\n"
            full_text.append("Catalog listing only; no product ranking requested.")
            _save_followup()
            yield f"data: {_json.dumps({'type': 'done'})}\\n\\n"
            return

        if flow in ("product_selection", "hybrid"):
            gen = stream_flow_a_recommendation(''',
        ),
    ],
    'tests/test_advisor_rules.py': [
        (
            '\nfrom api.chat import run_chat_turn\n',
            '\nfrom api.chat import run_chat_turn, _is_catalog_browse_request\n',
        ),
        (
            '        self.assertEqual(turn["_scenario_plan"]["requested_categories"], [])',
            '''        self.assertEqual(turn["_scenario_plan"]["requested_categories"], [])
        self.assertEqual(turn["_scenario_plan"]["flow"], "catalog_listing")
        self.assertTrue(_is_catalog_browse_request("Show all capture card products"))
        self.assertFalse(_is_catalog_browse_request("Recommend the best capture card for my setup"))''',
        ),
    ],
}

updated = {}
for name, source in files.items():
    for before, after in changes[name]:
        count = source.count(before)
        if count != 1:
            raise SystemExit(f'Refusing {name}: expected one match, found {count}: {before[:80]!r}')
        source = source.replace(before, after)
    updated[name] = source

stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup = root / '.codex-backups' / ('catalog-listing-' + stamp)
backup.mkdir(parents=True, exist_ok=False)
for name, source in files.items():
    target = backup / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)
for name, source in updated.items():
    (root / name).write_text(source)
print('Patched catalog listing; backup', backup)
"""


cmd = ["ssh", "-F", str(Path.home() / ".ssh" / "bzb_ovh_config"),
       "-o", "BatchMode=yes", "bzb-web01", "sudo", "-n", "python3", "-"]
subprocess.run(cmd, input=REMOTE.encode(), check=True)
