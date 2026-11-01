"""Turn the MAL ratings dump into per-user swipe matrices over the AniMatch catalogue.

MAL ratings (1-10) become the same actions as a list import in public/index.html:
>=8.5 super, >=6.5 like, <5 nope, otherwise seen. Users are split up front, so nobody in
the validation or test set contributes to any trained model.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

DATA = Path(__file__).parent / "data"
SEED = 42
MIN_RATINGS = 20
ACTION_WEIGHT = {"super": 2.0, "like": 1.0, "seen": 0.2, "nope": -0.7}  # WEIGHT in index.html


def to_action_code(r):
    """Codes: 3 super, 2 like, 1 seen, 0 nope. Same thresholds as toAction() on a 100 scale."""
    return np.select([r >= 8.5, r >= 6.5, r < 5], [3, 2, 0], default=1).astype(np.int8)


def main():
    catalog = json.loads((DATA / "catalog.json").read_text())
    mal_to_idx = {c["idMal"]: i for i, c in enumerate(catalog) if c["idMal"]}

    df = pd.read_csv(DATA / "rating_complete.csv", dtype={"user_id": "int32", "anime_id": "int32", "rating": "int8"})
    print(f"raw: {len(df):,} ratings, {df.user_id.nunique():,} users, {df.anime_id.nunique():,} anime")
    df["item"] = df.anime_id.map(mal_to_idx)
    in_catalog = df.dropna(subset=["item"]).copy()
    in_catalog["item"] = in_catalog["item"].astype(np.int32)
    in_catalog = in_catalog.drop_duplicates(["user_id", "item"])  # duplicates would be summed in the sparse matrix
    print(f"in catalogue: {len(in_catalog):,} ratings, {in_catalog.item.nunique():,} of {len(catalog)} titles")

    counts = in_catalog.groupby("user_id").size()
    users = counts[counts >= MIN_RATINGS].index.to_numpy(copy=True)
    rng = np.random.default_rng(SEED)
    rng.shuffle(users)
    in_catalog = in_catalog[in_catalog.user_id.isin(users)]

    n = len(users)
    n_test, n_val = int(n * 0.1), int(n * 0.1)
    splits = {"test": users[:n_test], "val": users[n_test:n_test + n_val], "train": users[n_test + n_val:]}
    for name, ids in splits.items():
        u_index = pd.Series(np.arange(len(ids)), index=ids)
        part = in_catalog[in_catalog.user_id.isin(ids)]
        rows = u_index.loc[part.user_id].to_numpy()
        # Stored as code + 1 so that a "nope" is not an implicit zero in the sparse matrix.
        m = sparse.csr_matrix(
            (to_action_code(part.rating.to_numpy()) + 1, (rows, part.item.to_numpy())),
            shape=(len(ids), len(catalog)), dtype=np.int8,
        )
        sparse.save_npz(DATA / f"{name}.npz", m)
        print(f"{name}: {m.shape[0]:,} users, {m.nnz:,} ratings")


if __name__ == "__main__":
    main()
