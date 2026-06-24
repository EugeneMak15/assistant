"""Quick test — process top 2 images from first 3 manuals to verify quality."""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os, json, zipfile, base64, time
from pathlib import Path
import truststore; truststore.inject_into_ssl()
from dotenv import load_dotenv; load_dotenv()
from openai import OpenAI

client = OpenAI()

PROMPT = """You are analyzing a page from an AV equipment manual.
Extract: connections, specs, compatibility notes, limitations, ports.
Return JSON: {"connections":[...], "specs":{}, "compatibility":[...], "limitations":[...], "ports":[...], "summary":"..."}
If decorative/logo/no tech info: {"skip":true, "reason":"..."}"""

manuals = sorted(Path('./manuals').glob('*.docx'))[:3]

for manual_path in manuals:
    print(f'\n=== {manual_path.name} ===')
    zf = zipfile.ZipFile(manual_path)
    entries = sorted(
        [e for e in zf.infolist()
         if 'media/' in e.filename
         and Path(e.filename).suffix.lower() in ('.png', '.jpg')
         and e.file_size > 5000],
        key=lambda e: e.file_size, reverse=True
    )[:2]

    for entry in entries:
        img = zf.read(entry.filename)
        b64 = base64.standard_b64encode(img).decode()
        fmt = "png" if img[:4] == b'\x89PNG' else "jpeg"

        resp = client.chat.completions.create(
            model='gpt-4o',
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': f'Manual: {manual_path.name}\n\n{PROMPT}'},
                {'type': 'image_url', 'image_url': {
                    'url': f'data:image/{fmt};base64,{b64}',
                    'detail': 'high'
                }}
            ]}],
            temperature=0.1,
            max_tokens=600,
            response_format={'type': 'json_object'}
        )
        result = json.loads(resp.choices[0].message.content)
        img_name = Path(entry.filename).name
        size_kb = entry.file_size // 1024
        print(f'  [{img_name}] {size_kb}KB')

        if result.get('skip'):
            print(f'    SKIP: {result.get("reason", "decorative")}')
        else:
            summary = result.get('summary', '')
            print(f'    Summary: {summary[:150]}')
            conns = result.get('connections', [])
            if conns:
                print(f'    Connections: {conns[:2]}')
            specs = result.get('specs', {})
            if specs:
                top_specs = dict(list(specs.items())[:3])
                print(f'    Specs: {top_specs}')
            limits = result.get('limitations', [])
            if limits:
                print(f'    Limitations: {limits[:2]}')
            ports = result.get('ports', [])
            if ports:
                print(f'    Ports: {ports[:5]}')
        time.sleep(0.3)
    zf.close()

print('\n=== Test complete ===')
