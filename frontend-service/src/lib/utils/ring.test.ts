import assert from 'node:assert/strict';
import { coverageTone, percent, ringDash } from './ring';

// A part of a known whole; an unknown whole is not 0 %
assert.equal(percent(1645, 2125)?.toFixed(1), '77.4');
assert.equal(percent(5, 0), null);
assert.equal(percent(null, 10), null);
assert.equal(percent(12, 10), 100);
// The arc: a quarter of the circle for 25 %, nothing for 0 or unknown, never past the full circle
const c = 2 * Math.PI * 10;
assert.equal(ringDash(25, 10), `${(c / 4).toFixed(1)} ${c.toFixed(1)}`);
assert.equal(ringDash(null, 10), `0.0 ${c.toFixed(1)}`);
assert.equal(ringDash(140, 10), `${c.toFixed(1)} ${c.toFixed(1)}`);
// Coverage tones
assert.equal(coverageTone(95), 'ok');
assert.equal(coverageTone(70), 'warn');
assert.equal(coverageTone(20), 'bad');
assert.equal(coverageTone(null), 'idle');
console.log('ring: OK');
