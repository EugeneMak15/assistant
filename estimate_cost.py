from pathlib import Path
from docx import Document

MANUALS_DIR = Path('./manuals')
files = [f for f in sorted(MANUALS_DIR.glob('*.docx')) if ' (2)' not in f.name]

total_words = 0
total_chunks = 0
CHUNK_MAX = 600
OVERLAP = 60

for path in files:
    try:
        doc = Document(path)
        text = ' '.join(p.text for p in doc.paragraphs if p.text.strip())
        words = len(text.split())
        total_words += words
        chunks = max(1, int(words / (CHUNK_MAX - OVERLAP)) + 1) if words > CHUNK_MAX else 1
        total_chunks += chunks
    except:
        pass

print(f"Manuals:      {len(files)}")
print(f"Total words:  {total_words:,}")
print(f"Est. chunks:  {total_chunks:,}")
print()

# Costs
tokens_per_chunk = 600 * 1.3
prompt_overhead = 400
input_tok  = total_chunks * (tokens_per_chunk + prompt_overhead)
output_tok = total_chunks * 60
embed_tok  = total_words * 1.3

input_cost  = input_tok  / 1e6 * 0.15
output_cost = output_tok / 1e6 * 0.60
embed_cost  = embed_tok  / 1e6 * 0.02
total_cost  = input_cost + output_cost + embed_cost

print("=== Cost estimate (GPT-4o-mini + text-embedding-3-small) ===")
print(f"GPT-4o-mini input:    {input_tok/1e6:.2f}M tokens = ${input_cost:.3f}")
print(f"GPT-4o-mini output:   {output_tok/1e6:.2f}M tokens = ${output_cost:.3f}")
print(f"Embeddings (3-small): {embed_tok/1e6:.2f}M tokens = ${embed_cost:.3f}")
print(f"TOTAL:                ~${total_cost:.2f}")
