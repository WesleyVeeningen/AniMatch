"""Offline evaluation with held-out users.

For each test user, N of their ratings play the role of swipes and the rest are hidden.
Each model ranks the deck (titles not swiped, sequels excluded, as in the app) and is
graded on how many hidden likes reach the top. Confidence intervals come from a paired
bootstrap over users, so the models are compared on identical people and splits.

NDCG flatters popular titles: a user can only be graded on what they chose to watch. AUC
therefore asks a question popularity helps with far less: among titles a user did watch,
are the ones they liked ranked above the ones they disliked?
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import sparse

from models import WEIGHTS, Content, EASE, Hybrid, ImplicitMF, ItemKNN, Popularity, PrunedEASE

DATA = Path(__file__).parent / "data"
RESULTS = Path(__file__).parent / "results"
K = 10


def sample_users(m, n_users, n_swipes, min_hidden_likes, seed):
    """Fixed (profile, hidden likes) cases, so every model sees the same ones."""
    rng = np.random.default_rng(seed)
    cases = []
    for u in rng.permutation(m.shape[0]):
        idx = m.indices[m.indptr[u]:m.indptr[u + 1]]
        codes = m.data[m.indptr[u]:m.indptr[u + 1]] - 1
        if len(idx) < n_swipes + min_hidden_likes:
            continue
        order = rng.permutation(len(idx))
        profile, rest = order[:n_swipes], order[n_swipes:]
        hidden = idx[rest][codes[rest] >= 2]
        if len(hidden) < min_hidden_likes:
            continue
        cases.append((idx[profile], WEIGHTS[codes[profile]], hidden, idx[rest][codes[rest] == 0]))
        if len(cases) == n_users:
            break
    return cases


def evaluate(model, cases, candidate):
    """Per-user NDCG@K, Recall@K and like/dislike AUC, plus the titles each user was shown."""
    discounts = 1 / np.log2(np.arange(2, K + 2))
    ndcg, recall, auc, shown = [], [], [], []
    for items, weights, hidden, disliked in cases:
        s = np.array(model.score(items, weights), dtype=np.float64)
        pairs = s[hidden][:, None] - s[disliked][None, :]
        auc.append(((pairs > 0).mean() + 0.5 * (pairs == 0).mean()) if len(disliked) >= 3 else np.nan)
        s[~candidate] = -np.inf
        s[items] = -np.inf
        top = np.argpartition(-s, K)[:K]
        top = top[np.argsort(-s[top])]
        hits = np.isin(top, hidden).astype(float)
        n_rel = int(candidate[hidden].sum())
        ideal = discounts[:min(n_rel, K)].sum()
        ndcg.append((hits * discounts).sum() / ideal if ideal else np.nan)
        recall.append(hits.sum() / min(n_rel, K) if n_rel else np.nan)
        shown.append(top)
    return np.array(ndcg), np.array(recall), np.array(shown), np.array(auc)


def paired_ci(a, b, n=2000, seed=0):
    """95% bootstrap interval for mean(a - b) over users."""
    ok = ~(np.isnan(a) | np.isnan(b))
    d = (a - b)[ok]
    rng = np.random.default_rng(seed)
    means = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(n)]
    return float(d.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def load():
    catalog = json.loads((DATA / "catalog.json").read_text())
    train = sparse.load_npz(DATA / "train.npz").tocsr()
    val = sparse.load_npz(DATA / "val.npz").tocsr()
    test = sparse.load_npz(DATA / "test.npz").tocsr()
    known = np.asarray((train != 0).sum(axis=0)).ravel() >= 50
    candidate = np.array([not c["sequel"] for c in catalog]) & known  # new titles have no ground truth to grade
    return catalog, train, val, test, known, candidate


def params(m):
    return {k: v for k, v in vars(m).items() if isinstance(v, (int, float))}


def tune(train, val, content, known, candidate, n_users):
    """Pick hyperparameters on validation users only. The test set stays untouched."""
    cases = sample_users(val, n_users, 20, 5, seed=1)
    best = {}
    grids = {
        "ease": [lambda v=v: EASE(lam=v) for v in (300, 1000, 3000, 10000, 30000, 100000, 300000)],
        "knn": [lambda k=k, a=a: ItemKNN(k=k, alpha=a) for k in (50, 200) for a in (0.3, 0.5, 0.7)],
        "mf": [lambda f=f, r=r: ImplicitMF(factors=f, reg=r) for f, r in ((32, 30), (64, 30), (64, 100), (128, 100))],
    }
    for name, grid in grids.items():
        scored = []
        for make in grid:
            m = make().fit(train)
            v = np.nanmean(evaluate(m, cases, candidate)[0])
            print(f"  {name} {params(m)} ndcg={v:.4f}", flush=True)
            scored.append((v, m))
        best[name] = max(scored, key=lambda x: x[0])[1]
    weights = {}
    for name, m in best.items():
        ws = [(np.nanmean(evaluate(Hybrid(m, content, known, w), cases, candidate)[0]), w)
              for w in (0.5, 0.7, 0.8, 0.9, 0.95, 1.0)]
        weights[name] = max(ws)[1]
        print(f"  hybrid {name}: " + " ".join(f"w={w}:{v:.4f}" for v, w in ws), flush=True)
    return best, weights


def cold_titles(train, val, catalog, known, candidate, content, lam, weight, n_users):
    """Can new titles still be recommended? Pretend the 2018-2020 titles have no ratings.

    CF is trained without them, which is the situation of every post-2020 title. The content
    model then ranks them alone, against a random order, and the curve shows what each
    cold_scale costs in accuracy for the exposure it buys. Uses validation users: this
    chooses a setting.
    """
    year = np.array([c["year"] or 0 for c in catalog])
    cold = (year >= 2018) & (year <= 2020) & candidate
    shipped = PrunedEASE(EASE(lam).fit((train @ sparse.diags((~cold).astype(np.float32))).tocsr().astype(np.int8)))
    cases = [c for c in sample_users(val, n_users, 20, 5, seed=4) if cold[c[2]].sum() >= 3]
    cases = [(c[0][~cold[c[0]]], c[1][~cold[c[0]]], c[2], c[3]) for c in cases]
    rng = np.random.default_rng(0)

    class Random:
        def score(self, items, weights):
            return rng.random(len(catalog))

    res = {"titles": int(cold.sum()), "users": len(cases), "catalogue_share": float(cold.sum() / candidate.sum()),
           "content_ndcg_within_cold": float(np.nanmean(evaluate(content, cases, cold)[0])),
           "random_ndcg_within_cold": float(np.nanmean(evaluate(Random(), cases, cold)[0])), "curve": []}
    for scale in (0.1, 0.5, 0.7, 0.8, 0.9, 1.0, 1.3, 1.6, 2.0):
        r = evaluate(Hybrid(shipped, content, known & ~cold, weight, scale), cases, candidate)
        res["curve"].append({"cold_scale": scale, "ndcg": float(np.nanmean(r[0])), "cold_share": float(cold[r[2]].mean())})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune-users", type=int, default=2000)
    ap.add_argument("--test-users", type=int, default=10000)
    args = ap.parse_args()

    catalog, train, val, test, known, candidate = load()
    print(f"titles with enough ratings: {known.sum()} of {len(catalog)}; candidates: {candidate.sum()}")
    content = Content(catalog)
    pop = Popularity().fit(train)
    print("tuning on validation users")
    best, weights = tune(train, val, content, known, candidate, args.tune_users)

    shipped = PrunedEASE(best["ease"])
    models = [pop, content, best["knn"], best["mf"], best["ease"], shipped,
              Hybrid(best["mf"], content, known, weights["mf"]), Hybrid(shipped, content, known, weights["ease"])]

    pop_rank = np.argsort(np.argsort(-pop.pop))
    out = {"tuned": {"ease_lam": best["ease"].lam, "knn_k": best["knn"].k, "knn_alpha": best["knn"].alpha,
                     "mf_factors": best["mf"].k, "mf_reg": best["mf"].reg, "hybrid_weights": weights},
           "catalog": len(catalog), "known_titles": int(known.sum()), "candidates": int(candidate.sum()),
           "rows": [], "differences": []}
    for n_swipes in (5, 10, 20, 50):
        cases = sample_users(test, args.test_users, n_swipes, 5, seed=2)
        per = {m.name: evaluate(m, cases, candidate) for m in models}
        base = per["Content (production)"]
        print(f"\n{n_swipes} swipes, {len(cases)} test users")
        for m in models:
            nd, re, shown, auc = per[m.name]
            row = {"swipes": n_swipes, "users": len(cases), "model": m.name, "ndcg": float(np.nanmean(nd)),
                   "recall": float(np.nanmean(re)), "auc": float(np.nanmean(auc)), "auc_users": int((~np.isnan(auc)).sum()),
                   "coverage": float(len(np.unique(shown)) / candidate.sum()),
                   "median_pop_rank": float(np.median(pop_rank[shown]))}
            out["rows"].append(row)
            d = paired_ci(nd, base[0])
            a = paired_ci(auc, base[3])
            out["differences"].append({"swipes": n_swipes, "model": m.name, "ndcg_vs_content": d, "auc_vs_content": a})
            print(f"  {m.name:32s} ndcg={row['ndcg']:.4f} recall={row['recall']:.4f} auc={row['auc']:.4f} cov={row['coverage']:.3f} "
                  f"poprank={row['median_pop_rank']:.0f}  vs content ndcg {d[0]:+.4f} [{d[1]:+.4f}, {d[2]:+.4f}] auc {a[0]:+.4f} [{a[1]:+.4f}, {a[2]:+.4f}]", flush=True)
    out["cold"] = cold_titles(train, val, catalog, known, candidate, content, best["ease"].lam, weights["ease"], 2000)
    print("\ncold titles:", out["cold"], flush=True)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "metrics.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
