import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()

from api.chain import build_chain, chain_to_text
from api.layer2 import get_chunks_for_candidates
from api.layer3 import get_recommendation

session = {
    'session_id': 'test',
    'venue_type': 'sport_bar',
    'num_inputs': 8,
    'num_outputs': 8,
    'resolution': '4K60',
    'max_distance_m': 50,
    'hdr_required': True,
    'category_hint': 'switcher',
}

print("Building chain...")
chain = build_chain(session)
chain_text = chain_to_text(chain)
print(chain_text)

all_candidates = []
seen = set()
for products in chain['roles'].values():
    for p in products:
        if p.id not in seen:
            all_candidates.append(p)
            seen.add(p.id)

print(f"\nCandidates: {[p.id for p in all_candidates]}")

print("\nFetching manual chunks...")
chunks = get_chunks_for_candidates(
    [p.id for p in all_candidates],
    query="8x8 matrix switcher 4K60 HDR HDBaseT extender 50m sport bar compatibility",
    chunks_per_candidate=4,
)
print(f"Got {len(chunks)} chunks from {len(set(c.product_id for c in chunks))} products")

print("\nGenerating recommendation...")
rec = get_recommendation(
    session_dict=session,
    candidates=all_candidates,
    chunks=chunks,
    chain_text=chain_text,
    question="I'm building a sport bar with 8 sources and 8 screens, 4K60, HDR, screens up to 50m away. What do I need?",
)
print()
print(rec[:2000])
