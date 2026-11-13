// Migration of components to Svelte 5 runes, file by file (svelte/compiler migrate, the engine of « sv migrate »).
//   node migrate-runes.mjs <file.svelte> [...]
// Prints, per file, what needs a look by hand: @migration-task notes, run() wrappers (former $: with side effects),
// createEventDispatcher still there.
import { readFileSync, writeFileSync } from 'node:fs';
import { migrate } from 'svelte/compiler';

let failed = 0;
for (const file of process.argv.slice(2)) {
  const source = readFileSync(file, 'utf8');
  if (/\$props\(|\$state\(|\$derived\(/.test(source)) { console.log(`skip (runes already) ${file}`); continue; }
  try {
    const { code } = migrate(source, { filename: file });
    if (code === source) { console.log(`unchanged ${file}`); continue; }
    writeFileSync(file, code);
    const notes = [];
    if (code.includes('@migration-task')) notes.push('migration-task');
    if (/\brun\(\(\) =>/.test(code)) notes.push('run()');
    if (code.includes('createEventDispatcher')) notes.push('dispatcher');
    if (/\$bindable\(/.test(code)) notes.push('bindable');
    console.log(`migrated ${file}${notes.length ? '  [' + notes.join(', ') + ']' : ''}`);
  } catch (error) {
    failed += 1;
    console.log(`FAILED ${file}: ${String(error.message || error).split('\n')[0]}`);
  }
}
process.exitCode = failed ? 1 : 0;
