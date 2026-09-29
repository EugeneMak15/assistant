"""Audit catalog/interface contradictions; optionally repair high-confidence false resolutions.

Usage: python audit_catalog_specs.py --db products.db [--apply]
The default mode is read-only. Ambiguous records are reported, never changed.
"""

import argparse
import json
import sqlite3


def audit(db_path: str, apply: bool = False) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    summary = {"false_8k": [], "false_4k120": [], "ndi_conflicts": [], "updated": []}
    rows = conn.execute("""SELECT p.id, p.name, p.product_url, p.resolutions, p.output_signals,
                                  pi.max_res, pi.supports_8k, pi.out_ndi
                           FROM products p JOIN product_interfaces pi ON pi.sku=p.id""").fetchall()
    for row in rows:
        sku = row["id"]
        resolutions = json.loads(row["resolutions"] or "[]")
        signals = json.loads(row["output_signals"] or "[]")
        max_res = (row["max_res"] or "").upper()
        false_8k = row["supports_8k"] == 0 and any(r.upper().startswith("8K") for r in resolutions)
        false_4k120 = max_res in {"1080P", "1080P60", "4K30", "4K60"} and any(r.upper() == "4K120" for r in resolutions)
        if false_8k:
            summary["false_8k"].append(sku)
        if false_4k120:
            summary["false_4k120"].append(sku)
        if ("NDI" in signals) != bool(row["out_ndi"]):
            summary["ndi_conflicts"].append(sku)

        # A named 8K product may have a wrong interface record. Flag it for
        # manual review instead of silently changing customer-facing specs.
        name_upper = (row["name"] or "").upper()
        clear_4k_product = "8K" not in name_upper
        corrected = [r for r in resolutions if not (
            false_8k and clear_4k_product and r.upper().startswith("8K")
        ) and not (false_4k120 and "4K120" not in name_upper and r.upper() == "4K120")]
        if apply and corrected != resolutions:
            conn.execute("UPDATE products SET resolutions=? WHERE id=?", (json.dumps(corrected), sku))
            summary["updated"].append(sku)
        if apply and sku == "BG-STREAM-E":
            # This URL selects the Dante-ready variant; the NDI variant is BG-STREAM-NE.
            if "technology=dante" in (row["product_url"] or "").lower():
                conn.execute("UPDATE product_interfaces SET out_ndi=0 WHERE sku=?", (sku,))
                corrected_signals = [s for s in signals if s != "NDI"]
                conn.execute("UPDATE products SET output_signals=? WHERE id=?", (json.dumps(corrected_signals), sku))
                summary["updated"].append(sku)
        elif apply and ("NDI" in signals) != bool(row["out_ndi"]):
            # The interface row is variant-specific; output_signals was scraped
            # from a shared family page and can include other variants' NDI.
            corrected_signals = [s for s in signals if s != "NDI"]
            if row["out_ndi"]:
                corrected_signals.append("NDI")
            conn.execute("UPDATE products SET output_signals=? WHERE id=?", (json.dumps(corrected_signals), sku))
            summary["updated"].append(sku)
        if apply and sku == "BG-IPGEAR-XTREME-CORE" and "4K120" in name_upper:
            conn.execute("UPDATE product_interfaces SET max_res='4K120' WHERE sku=?", (sku,))
            summary["updated"].append(sku)
    if apply:
        conn.commit()
    conn.close()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.db, args.apply), indent=2))
