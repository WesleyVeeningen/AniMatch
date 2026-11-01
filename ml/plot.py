"""Charts for the README, from results/metrics.json."""
import json
from pathlib import Path

import matplotlib.pyplot as plt

RESULTS = Path(__file__).parent / "results"
m = json.loads((RESULTS / "metrics.json").read_text())
SHIPPED = "Hybrid (EASE (top 100 links))"
SERIES = {SHIPPED: ("Hybrid (shipped)", "#d6336c"), "Popularity": ("Popularity", "#868e96"),
          "Content (production)": ("Content (previous)", "#1c7ed6")}

plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for ax, key, label in ((axes[0], "ndcg", "NDCG@10"), (axes[1], "auc", "Like vs dislike AUC")):
    for model, (name, color) in SERIES.items():
        rows = [r for r in m["rows"] if r["model"] == model]
        ax.plot([r["swipes"] for r in rows], [r[key] for r in rows], "o-", color=color, label=name)
    ax.set(xlabel="Swipes so far", ylabel=label, xscale="log", xticks=[5, 10, 20, 50], xticklabels=[5, 10, 20, 50])
    ax.minorticks_off()
axes[0].legend(frameon=False, loc="center right", bbox_to_anchor=(1, 0.42))
fig.tight_layout()
fig.savefig(RESULTS / "accuracy.png", dpi=150)

curve = m["cold"]["curve"]
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot([c["cold_share"] for c in curve], [c["ndcg"] for c in curve], "o-", color="#d6336c")
for c in curve:
    if c["cold_scale"] == 1.3:
        ax.annotate("shipped (1.3)", (c["cold_share"], c["ndcg"]), xytext=(10, 6), textcoords="offset points")
ax.axvline(m["cold"]["catalogue_share"], color="#868e96", ls="--")
ax.set(xlabel="Share of top 10 that is new titles", ylabel="NDCG@10")
fig.tight_layout()
fig.savefig(RESULTS / "new_titles.png", dpi=150)
