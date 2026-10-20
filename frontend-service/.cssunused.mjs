import { compile, preprocess } from 'svelte/compiler';
import config from './svelte.config.js';
import { readFileSync, readdirSync, statSync, writeFileSync } from 'fs';
import { join } from 'path';
const walk = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? walk(p) : p.endsWith('.svelte') ? [p] : []; });
let total = 0; const out = {};
for (const f of walk('src')) {
  const src = readFileSync(f, 'utf8');
  try {
    const pre = await preprocess(src, config.preprocess, { filename: f });
    const { warnings } = compile(pre.code, { filename: f, generate: false });
    const w = warnings.filter((x) => x.code === 'css_unused_selector');
    if (w.length) { out[f] = w.map((x) => x.message.split('\n')[0]); total += w.length; }
  } catch (e) { out[f] = ['COMPILE_ERROR ' + e.message.slice(0, 80)]; }
}
writeFileSync(process.argv[2], JSON.stringify(out, null, 1));
for (const [f, w] of Object.entries(out).sort((a, b) => b[1].length - a[1].length)) console.log(w.length, f);
console.log('total', total);
