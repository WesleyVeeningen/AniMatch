// Hybrid recommender: collaborative filtering (EASE) for titles the rating data covers,
// the genre/tag profile for everything newer. Trained and evaluated in ml/.
// WEIGHT, CF_WEIGHT and COLD_SCALE must match ml/prepare.py and ml/models.py (ml/test_parity.mjs checks).

// 'seen' = imported from a list as watched but rated middling
const WEIGHT = {like: 1, super: 2, nope: -0.7, seen: 0.2};
const CF_WEIGHT = 0.9;   // share of the CF score for titles it knows
const COLD_SCALE = 1.3;  // how far content alone can lift a title CF has never seen

function contentScore(f, averageScore, tags) {
  let dot = 0, norm = 0;
  for (const k in f) { dot += (tags[k] || 0) * f[k]; norm += f[k] ** 2; }
  const quality = ((averageScore || 65) - 70) / 30;
  return dot / Math.sqrt(norm || 1) + 0.08 * quality;
}

const meanStd = values => {
  let sum = 0, sq = 0, n = 0;
  for (const v of values) { sum += v; sq += v * v; n++; }
  const mean = sum / (n || 1);
  return [mean, Math.sqrt(Math.max(0, sq / (n || 1) - mean * mean)) + 1e-9];
};

function indexCF(raw) {
  return {...raw, index: new Map(raw.ids.map((id, i) => [id, i]))};
}

// Everything that depends on the swipe history, computed once per ranking.
// `titles` is every loaded anime, as {f, averageScore}.
function buildPrefs(history, titles, cf) {
  const tags = {};
  for (const h of history) for (const k in h.f) tags[k] = (tags[k] || 0) + WEIGHT[h.a] * h.f[k];
  const n = Math.max(1, history.length);
  for (const k in tags) tags[k] /= n;

  const [cMean, cStd] = meanStd(titles.map(m => contentScore(m.f, m.averageScore, tags)));
  const p = {tags, cMean, cStd, cf: null};
  if (!cf) return p;
  const known = history.filter(h => cf.index.has(h.id));
  if (!known.length) return p;

  const scores = new Float64Array(cf.ids.length);
  for (const h of known) {
    const i = cf.index.get(h.id), links = cf.links[i], w = cf.w[i];
    for (let j = 0; j < links.length; j++) scores[links[j]] += w[j] * cf.scale * WEIGHT[h.a];
  }
  const [fMean, fStd] = meanStd(scores);
  return {...p, cf: {model: cf, scores, fMean, fStd}};
}

function hybridScore(id, f, averageScore, p) {
  const z = (contentScore(f, averageScore, p.tags) - p.cMean) / p.cStd;
  if (!p.cf) return z;
  const i = p.cf.model.index.get(id);
  if (i === undefined) return COLD_SCALE * z;
  return CF_WEIGHT * (p.cf.scores[i] - p.cf.fMean) / p.cf.fStd + (1 - CF_WEIGHT) * z;
}

// The liked title that pushed this recommendation up the most, if any.
function becauseOf(id, history, p) {
  if (!p.cf) return null;
  const { model } = p.cf, target = model.index.get(id);
  if (target === undefined) return null;
  let best = null, top = 0;
  for (const h of history) {
    if (h.a !== 'like' && h.a !== 'super') continue;
    const i = model.index.get(h.id);
    if (i === undefined) continue;
    const j = model.links[i].indexOf(target);
    if (j >= 0 && model.w[i][j] * WEIGHT[h.a] > top) { top = model.w[i][j] * WEIGHT[h.a]; best = h; }
  }
  return best;
}

if (typeof module !== 'undefined') module.exports = {WEIGHT, buildPrefs, hybridScore, becauseOf, indexCF};
