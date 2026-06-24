from docx import Document
from pathlib import Path

MANUALS_DIR = Path('./manuals')
files = sorted(MANUALS_DIR.glob('*.docx'))
files = [f for f in files if '(2)' not in f.name]

sizes = []
for f in files:
    try:
        doc = Document(f)
        words = len(' '.join(p.text for p in doc.paragraphs if p.text.strip()).split())
        size_kb = f.stat().st_size // 1024
        sizes.append((f.name[:42], words, size_kb))
    except:
        pass

sizes.sort(key=lambda x: -x[2])
print(f"{'File':<44} {'Words':>7} {'KB':>7}")
print('-' * 62)
for name, w, kb in sizes[:20]:
    print(f"{name:<44} {w:>7,} {kb:>7,}")

total_w = sum(x[1] for x in sizes)
total_kb = sum(x[2] for x in sizes)
avg_w = total_w // len(sizes)
avg_kb = total_kb // len(sizes)
ratio = total_w / (total_kb or 1)

print()
print(f"Files:    {len(sizes)}")
print(f"Total words extracted: {total_w:,}")
print(f"Total file size:       {total_kb:,} KB  ({total_kb//1024} MB)")
print(f"Avg per manual:        {avg_w:,} words  /  {avg_kb:,} KB")
print(f"Text density:          {ratio:.1f} words/KB  (low = lots of images/diagrams)")
