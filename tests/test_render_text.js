// Run with: node tests/test_render_text.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'chat.html'), 'utf8');
const start = html.indexOf('function renderText(text) {');
const end = html.indexOf('// ─── Parse and render final recommendation text', start);
assert(start >= 0 && end > start);
const renderText = new Function('resolveSkuUrl', `${html.slice(start, end)}; return renderText;`)(() => null);

const linked = renderText('[BG-EPTZ-UH4K](https://bzbgear.com/product/example/)');
assert.match(linked, /<a href="https:\/\/bzbgear\.com\/product\/example\/"/);
assert.match(linked, />BG-EPTZ-UH4K<\/a>/);
assert.equal((linked.match(/<a /g) || []).length, 1);
assert.doesNotMatch(renderText('[x](https://evil.example/<script>)'), /<script>/);
console.log('renderText links OK');
