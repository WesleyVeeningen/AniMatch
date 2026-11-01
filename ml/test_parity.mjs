// The browser must rank exactly like the model that was evaluated. Run: node ml/test_parity.mjs
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { buildPrefs, hybridScore, becauseOf, indexCF } = require('../public/recommender.js');
const read = p => JSON.parse(readFileSync(new URL(p, import.meta.url)));

const cf = indexCF(read('../public/cf-model.json'));
const { titles, cases } = read('./results/parity_fixture.json');

let worst = 0, compared = 0;
for (const c of cases) {
  const p = buildPrefs(c.history, titles, cf);
  titles.forEach((t, i) => {
    worst = Math.max(worst, Math.abs(hybridScore(t.id, t.f, t.averageScore, p) - c.scores[i]));
    compared++;
  });
}
console.log(`${cases.length} profiles, ${compared} scores, largest difference ${worst.toExponential(2)}`);
if (worst > 1e-3) throw new Error('browser scores differ from the evaluated model');

// Without the model file the app still has to work, on content alone.
const fallback = buildPrefs(cases[0].history, titles, null);
if (fallback.cf || !Number.isFinite(hybridScore(titles[0].id, titles[0].f, titles[0].averageScore, fallback)))
  throw new Error('content fallback broken');
if (buildPrefs([], titles, cf).cf !== null) throw new Error('empty history should not use CF');

const p = buildPrefs(cases[0].history, titles, cf);
const reasons = titles.map(t => becauseOf(t.id, cases[0].history, p)).filter(Boolean);
if (!reasons.length) throw new Error('becauseOf found no reasons');
if (!reasons.every(h => h.a === 'like' || h.a === 'super')) throw new Error('becauseOf cited a non-like');
console.log('ok');
