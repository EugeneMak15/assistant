import sys; sys.stdout.reconfigure(encoding='utf-8')
import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()
from api.chain import build_chain, chain_to_text

print("=== Sport bar: 8x8, 4K60, 50m ===")
chain = build_chain({'venue_type':'sport_bar','num_inputs':8,'num_outputs':8,
                     'resolution':'4K60','max_distance_m':50,'category_hint':'switcher'})
print(chain_to_text(chain))
print("Issues:", chain['issues'])

print()
print("=== Conference room: 2 sources, 1 display, no distance ===")
chain2 = build_chain({'venue_type':'conference_room','num_inputs':2,'num_outputs':1,
                      'resolution':'4K60','max_distance_m':3,'category_hint':'switcher'})
print(chain_to_text(chain2))

print()
print("=== PTZ camera system ===")
chain3 = build_chain({'venue_type':'studio','category_hint':'camera'})
print(chain_to_text(chain3))
