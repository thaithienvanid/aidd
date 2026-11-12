// Parses every Mermaid block in the repository's Markdown with Mermaid itself, so a diagram GitHub cannot render
// fails CI. Run from the repository root: node tools/mermaid/check-mermaid.mjs
import { JSDOM } from 'jsdom';
import fs from 'fs'; import path from 'path'; import { execSync } from 'child_process';
const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.window = dom.window; globalThis.document = dom.window.document;
try { globalThis.navigator = dom.window.navigator; } catch {}
const { default: mermaid } = await import('mermaid');
mermaid.initialize({ startOnLoad: false });
const root = process.argv[2] ?? ".";
const files = execSync('git ls-files "*.md"', { cwd: root }).toString().trim().split('\n');
let n = 0, bad = 0;
for (const f of files) {
  const t = fs.readFileSync(path.join(root, f), 'utf8');
  for (const m of t.matchAll(/```mermaid\n([\s\S]*?)```/g)) {
    n++;
    try { await mermaid.parse(m[1]); } catch (e) { bad++; console.log('FAIL', f, '\n', String(e.message || e).split('\n').slice(0, 4).join('\n')); }
  }
}
console.log(`${n - bad}/${n} mermaid blocks parse`);
if (bad) process.exit(1);
