"""Peek at first 400 chars of each 'other' category manual to classify manually."""
import sqlite3
from pathlib import Path
from docx import Document

MANUALS_DIR = Path("./manuals")
conn = sqlite3.connect("products.db")
others = [r[0] for r in conn.execute("SELECT id FROM products WHERE category='other' ORDER BY id")]
conn.close()

for pid in others:
    # find matching file
    files = list(MANUALS_DIR.glob(f"*{pid}*"))
    if not files:
        print(f"\n{pid}: FILE NOT FOUND")
        continue
    try:
        doc = Document(files[0])
        text = " | ".join(p.text.strip() for p in doc.paragraphs if p.text.strip())[:400]
    except Exception as e:
        text = f"ERROR: {e}"
    print(f"\n[{pid}]\n  file: {files[0].name}\n  text: {text}")
