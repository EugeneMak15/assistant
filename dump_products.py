import sqlite3, json
from collections import Counter

conn = sqlite3.connect('products.db')
conn.row_factory = sqlite3.Row

cats = conn.execute('SELECT category, COUNT(*) c FROM products GROUP BY category ORDER BY c DESC').fetchall()
print('=== CATEGORIES ===')
for r in cats:
    print(f'  {r["category"]}: {r["c"]} products')

print('\n=== SIGNAL TYPES ===')
rows = conn.execute('SELECT input_signals, output_signals FROM products').fetchall()
sigs = Counter()
for r in rows:
    for field in [r['input_signals'], r['output_signals']]:
        try:
            for s in json.loads(field or '[]'): sigs[s] += 1
        except: pass
for s, c in sigs.most_common(25):
    print(f'  {s}: {c}')

print('\n=== RESOLUTIONS ===')
rows = conn.execute('SELECT resolutions FROM products').fetchall()
res = Counter()
for r in rows:
    try:
        for s in json.loads(r['resolutions'] or '[]'): res[s] += 1
    except: pass
for s, c in res.most_common():
    print(f'  {s}: {c}')

print('\n=== DISTANCE RANGE ===')
rows = conn.execute('SELECT max_distance_m FROM products WHERE max_distance_m IS NOT NULL ORDER BY max_distance_m').fetchall()
dists = [r['max_distance_m'] for r in rows]
if dists: print(f'  min={min(dists)}m  max={max(dists)}m  values={sorted(set(dists))}')

print('\n=== KEY PRODUCTS BY CATEGORY ===')
for cat in ['camera','switcher','extender','av_over_ip','sdi','encoder_decoder','controller','distribution_amp','kvm_switch','multiviewer']:
    rows = conn.execute(
        'SELECT id, title, input_signals, output_signals, resolutions, max_distance_m, inputs, outputs, what_it_does FROM products WHERE category=? ORDER BY id LIMIT 5',
        (cat,)
    ).fetchall()
    print(f'\n-- {cat} --')
    for r in rows:
        ins  = json.loads(r['input_signals']  or '[]')
        outs = json.loads(r['output_signals'] or '[]')
        res  = json.loads(r['resolutions']    or '[]')
        wd   = (r['what_it_does'] or '')[:80]
        print(f'  {r["id"]}')
        print(f'    signals: in={ins} out={outs}')
        print(f'    res={res}  dist={r["max_distance_m"]}m  io={r["inputs"]}x{r["outputs"]}')
        if wd: print(f'    desc: {wd}')

conn.close()
