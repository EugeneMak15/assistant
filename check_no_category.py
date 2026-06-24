import sys; sys.stdout.reconfigure(encoding='utf-8')
import xml.etree.ElementTree as ET

FEED_PATH = r"C:\Users\eugen\Downloads\download.rss"
tree = ET.parse(FEED_PATH)
root = tree.getroot()

no_cat = []
has_cat = []

for item in root.findall(".//item"):
    pid = (item.findtext("id") or "").strip()
    title = (item.findtext("title") or "")[:70]

    cats_el = item.find("categories")
    cats = []
    if cats_el is not None:
        cats = [el.text.strip() for el in cats_el.findall("category") if el.text]

    if not cats:
        no_cat.append((pid, title))
    else:
        has_cat.append((pid, cats))

print(f"With categories:    {len(has_cat)}")
print(f"Without categories: {len(no_cat)}")

print("\n=== SAMPLE WITHOUT CATEGORIES (first 20) ===")
for pid, title in no_cat[:20]:
    print(f"  {pid:<30} {title}")

print("\n=== ALL UNIQUE CATEGORY PATHS ===")
all_cats = set()
for _, cats in has_cat:
    for c in cats:
        all_cats.add(c)
for c in sorted(all_cats):
    print(f"  {c}")
