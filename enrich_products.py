"""
Enrich products DB with AI-generated:
  - what_it_does: clean 1-2 sentence explanation
  - use_cases: 5-10 specific real-world scenarios

Uses GPT-4o-mini. Cost: ~$0.15 for all 429 products.
Results are cached in DB so re-runs are free.
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3, json, re, time
from bs4 import BeautifulSoup

import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()
from openai import OpenAI
from rich.console import Console
from rich.progress import track

console = Console()
client = OpenAI()
DB_PATH = "./products.db"

SYSTEM = """You are a technical AV equipment expert writing a product catalog for installers, integrators, and AV consultants.

For each product you receive, write TWO things:

1. what_it_does: 1-2 clear sentences explaining exactly what this device does technically.
   Be specific — mention signal types, port counts, distances, key capabilities.
   NO marketing fluff. NO "introducing the..." or "Overview" or generic phrases.
   Example: "8x8 HDMI 2.0 matrix switcher that routes any of 8 sources to any of 8 displays independently, with 18Gbps bandwidth supporting 4K60 HDR."

2. use_cases: list of 5-10 SPECIFIC real-world scenarios where this product is used.
   Each item should name a real venue/environment + what problem it solves.
   Be concrete — use real numbers from the specs when relevant.
   Format: plain text lines, no dashes or bullets.

Return JSON only:
{
  "what_it_does": "...",
  "use_cases": ["scenario 1", "scenario 2", ...]
}"""


def build_prompt(p: dict) -> str:
    title = p.get("title") or p.get("name") or ""
    cat   = p.get("category") or ""
    site_cat = " > ".join(filter(None, [p.get("site_category"), p.get("site_subcategory")]))

    specs = json.loads(p.get("specs_json") or "{}")
    feats = json.loads(p.get("features") or "[]")

    # Clean specs — remove empty/useless rows
    spec_lines = [f"{k}: {v}" for k, v in specs.items()
                  if k and v and "technical spec" not in k.lower()
                  and len(str(v)) > 1][:20]

    # Clean features — strip HTML leftovers
    feat_lines = []
    for f in feats[:10]:
        clean = re.sub(r'\s+', ' ', f).strip()
        if len(clean) > 5 and len(clean) < 300:
            feat_lines.append(clean)

    price = p.get("price_usd")
    inp   = p.get("inputs")
    out   = p.get("outputs")
    dist  = p.get("max_distance_m")
    bw    = p.get("max_bandwidth_gbps")
    res   = json.loads(p.get("resolutions") or "[]")
    sigs  = json.loads(p.get("input_signals") or "[]")

    lines = [
        f"SKU: {p['id']}",
        f"Title: {title}",
        f"Category: {cat} ({site_cat})",
    ]
    if inp or out: lines.append(f"Ports: {inp or '?'} inputs x {out or '?'} outputs")
    if dist:  lines.append(f"Max distance: {dist}m")
    if bw:    lines.append(f"Bandwidth: {bw}Gbps")
    if res:   lines.append(f"Resolutions: {', '.join(res)}")
    if sigs:  lines.append(f"Signals: {', '.join(sigs)}")
    if price: lines.append(f"Price: ${price:,.0f}")

    if spec_lines:
        lines.append("\nKey specs:")
        lines.extend(spec_lines[:12])

    if feat_lines:
        lines.append("\nFeatures:")
        lines.extend(feat_lines[:8])

    return "\n".join(lines)


def call_gpt(prompt: str) -> dict:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def migrate(conn):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    for col in ["what_it_does", "use_cases"]:
        if col not in existing:
            conn.execute(f"ALTER TABLE products ADD COLUMN {col} TEXT")
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    migrate(conn)

    # Load products that haven't been enriched yet
    rows = conn.execute("""
        SELECT * FROM products
        WHERE what_it_does IS NULL OR what_it_does = ''
        ORDER BY category, id
    """).fetchall()

    total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    already = total - len(rows)
    console.print(f"Total products: {total}  |  Already enriched: {already}  |  To process: {len(rows)}")

    if not rows:
        console.print("[green]All products already enriched![/green]")
        conn.close()
        return

    errors = 0
    for i, row in enumerate(rows):
        p = dict(row)
        pid = p["id"]

        try:
            prompt = build_prompt(p)
            result = call_gpt(prompt)

            what  = result.get("what_it_does", "").strip()
            cases = result.get("use_cases", [])
            if isinstance(cases, list):
                cases_json = json.dumps(cases)
            else:
                cases_json = json.dumps([str(cases)])

            conn.execute(
                "UPDATE products SET what_it_does=?, use_cases=? WHERE id=?",
                (what, cases_json, pid)
            )
            conn.commit()

        except Exception as e:
            console.print(f"[red]Error on {pid}: {e}[/red]")
            errors += 1
            time.sleep(2)
            continue

        # Progress every 10
        if (i + 1) % 10 == 0:
            console.print(f"  [{i+1}/{len(rows)}] Last: {pid} — {what[:60]}...")

        time.sleep(0.15)  # ~7 req/sec, well under limits

    conn.close()
    console.print(f"\n[bold green]Done! {len(rows) - errors} enriched, {errors} errors.[/bold green]")


if __name__ == "__main__":
    main()
