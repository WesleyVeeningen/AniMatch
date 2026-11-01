"""Write the browser model and a parity fixture.

public/cf-model.json holds the pruned EASE links, keyed by AniList id. test_parity.mjs then
scores the fixture profiles with public/recommender.js and must match Python exactly.
"""
import json
from pathlib import Path

import numpy as np

from evaluate import load, sample_users
from models import WEIGHTS, Content, EASE, Hybrid, PrunedEASE

ROOT = Path(__file__).parent
PUBLIC_MODEL = ROOT.parent / "public" / "cf-model.json"
FIXTURE = ROOT / "results" / "parity_fixture.json"
ACTIONS = {-0.7: "nope", 0.2: "seen", 1.0: "like", 2.0: "super"}


def main():
    metrics = json.loads((ROOT / "results" / "metrics.json").read_text())["tuned"]
    catalog, train, val, test, known, candidate = load()
    pruned = PrunedEASE(EASE(metrics["ease_lam"]).fit(train))

    # Links from or to titles below the rating threshold are too noisy to keep.
    Q = pruned.Q.copy()
    Q[~known, :] = 0
    Q[:, ~known] = 0
    pruned.B = Q.astype(np.float32) * pruned.scale

    ids = np.flatnonzero(known)
    position = -np.ones(len(catalog), dtype=int)
    position[ids] = np.arange(len(ids))
    links, w = [], []
    for i in ids:
        t = np.flatnonzero(Q[i])
        links.append(position[t].tolist())
        w.append(Q[i, t].tolist())
    model = {"ids": [catalog[i]["id"] for i in ids], "scale": pruned.scale, "links": links, "w": w}
    PUBLIC_MODEL.write_text(json.dumps(model, separators=(",", ":")))
    print(f"{PUBLIC_MODEL.name}: {PUBLIC_MODEL.stat().st_size / 1024:.0f} KB, {len(ids)} titles, {(Q != 0).sum():,} links")

    content = Content(catalog)
    hybrid = Hybrid(pruned, content, known, metrics["hybrid_weights"]["ease"])
    cases = sample_users(test, 25, 20, 5, seed=5)
    fixture = {"titles": [{"id": c["id"], "f": c["f"], "averageScore": c["averageScore"]} for c in catalog], "cases": []}
    for items, weights, *_ in cases:
        keep = known[items]  # the browser model has no rows for unknown titles
        items_k, weights_k = items[keep], weights[keep]
        fixture["cases"].append({
            "history": [{"id": catalog[i]["id"], "a": ACTIONS[round(float(x), 1)], "f": catalog[i]["f"]}
                        for i, x in zip(items_k, weights_k)],
            "scores": hybrid.score(items_k, weights_k).tolist(),
        })
    FIXTURE.write_text(json.dumps(fixture))


if __name__ == "__main__":
    main()
