"""Recommenders under comparison. Each scores every catalogue title for one user.

All models take the same input as the app has: a list of (item index, swipe weight)
pairs for a user the model has never seen. Nothing here needs retraining per user.
"""
import numpy as np
from scipy import sparse

from prepare import ACTION_WEIGHT

WEIGHTS = np.array([ACTION_WEIGHT[a] for a in ("nope", "seen", "like", "super")])  # by action code


def positive_matrix(codes):
    """Binary likes from a stored action matrix (stored value = code + 1)."""
    m = codes.copy().tocsr()
    m.data = (m.data >= 3).astype(np.float32)
    m.eliminate_zeros()
    return m


class Popularity:
    """Most-liked titles in training. Ignores the user entirely."""
    name = "Popularity"

    def fit(self, train):
        self.pop = np.asarray(positive_matrix(train).sum(axis=0)).ravel().astype(np.float64)
        return self

    def score(self, items, weights):
        return self.pop


class Content:
    """Exact port of prefs() and score() in public/index.html."""
    name = "Content (production)"

    def __init__(self, catalog):
        vocab = {k: i for i, k in enumerate(sorted({k for c in catalog for k in c["f"]}))}
        rows, cols, vals = [], [], []
        for i, c in enumerate(catalog):
            for k, v in c["f"].items():
                rows.append(i), cols.append(vocab[k]), vals.append(v)
        self.F = sparse.csr_matrix((vals, (rows, cols)), shape=(len(catalog), len(vocab)))
        norm = np.sqrt(np.asarray(self.F.multiply(self.F).sum(axis=1)).ravel())
        self.norm = np.where(norm > 0, norm, 1)
        self.quality = np.array([((c["averageScore"] or 65) - 70) / 30 for c in catalog])

    def fit(self, train):
        return self

    def score(self, items, weights):
        p = self.F[items].T.dot(weights) / max(1, len(items))
        return self.F.dot(p) / self.norm + 0.08 * self.quality


class ItemKNN:
    """Cosine similarity between titles, kept to the top k neighbours of each."""
    name = "Item-kNN"

    def __init__(self, k=100, alpha=0.5):
        self.k, self.alpha = k, alpha

    def fit(self, train):
        X = positive_matrix(train)
        counts = np.asarray(X.sum(axis=0)).ravel()
        d = 1 / np.power(np.maximum(counts, 1), self.alpha)
        S = (X.T @ X).toarray().astype(np.float32) * d[None, :] * d[:, None]
        np.fill_diagonal(S, 0)
        cut = np.partition(S, -self.k, axis=1)[:, -self.k][:, None]
        self.S = np.where(S >= cut, S, 0)
        return self

    def score(self, items, weights):
        return self.S[items].T.dot(weights)


class EASE:
    """Steck 2019: a closed-form linear item-item model with a zero diagonal."""
    name = "EASE"

    def __init__(self, lam=300.0):
        self.lam = lam

    def fit(self, train):
        X = positive_matrix(train)
        G = (X.T @ X).toarray().astype(np.float64)
        G[np.diag_indices_from(G)] += self.lam
        P = np.linalg.inv(G)
        B = P / (-np.diag(P))
        np.fill_diagonal(B, 0)
        self.B = B.astype(np.float32)
        return self

    def score(self, items, weights):
        return self.B[items].T.dot(weights)


class PrunedEASE:
    """What the browser actually runs: the strongest n links per title, rounded to int8."""

    def __init__(self, ease, n=100):
        self.name = f"EASE (top {n} links)"
        B = ease.B
        cut = np.partition(np.abs(B), -n, axis=1)[:, -n][:, None]
        P = np.where(np.abs(B) >= cut, B, 0)
        self.scale = float(np.abs(P).max() / 127)
        self.Q = np.rint(P / self.scale).astype(np.int8)
        self.B = self.Q.astype(np.float32) * self.scale

    def score(self, items, weights):
        return self.B[items].T.dot(weights)


class ImplicitMF:
    """iALS matrix factorisation. New users are folded in with one ridge solve."""
    name = "Implicit MF"

    def __init__(self, factors=64, reg=30.0, alpha=10.0, iters=6, seed=0):
        self.k, self.reg, self.alpha, self.iters, self.seed = factors, reg, alpha, iters, seed

    def _solve(self, X, Y):
        """Update one side of the factorisation given the other, one row at a time."""
        k = Y.shape[1]
        YtY = Y.T @ Y
        out = np.zeros((X.shape[0], k), dtype=np.float32)
        for u in range(X.shape[0]):
            idx = X.indices[X.indptr[u]:X.indptr[u + 1]]
            if len(idx) == 0:
                continue
            Yu = Y[idx]
            A = YtY + self.alpha * Yu.T @ Yu + self.reg * np.eye(k)
            out[u] = np.linalg.solve(A, (1 + self.alpha) * Yu.sum(axis=0))
        return out

    def fit(self, train):
        rng = np.random.default_rng(self.seed)
        X = positive_matrix(train)
        Xt = X.T.tocsr()
        V = rng.normal(0, 0.1, (X.shape[1], self.k)).astype(np.float32)
        for it in range(self.iters):
            U = self._solve(X, V)
            V = self._solve(Xt, U)
        self.V = V.astype(np.float64)
        self.VtV = self.V.T @ self.V
        return self

    def score(self, items, weights):
        items, weights = np.asarray(items), np.asarray(weights)
        pos = weights > 0
        if not pos.any():
            return np.zeros(self.V.shape[0])
        Yu = self.V[items[pos]]
        conf = self.alpha * weights[pos]
        A = self.VtV + (Yu.T * conf) @ Yu + self.reg * np.eye(self.k)
        u = np.linalg.solve(A, ((1 + conf)[:, None] * Yu).sum(axis=0))
        return self.V.dot(u)


class Hybrid:
    """Rank-free blend of a CF model and the content model.

    Both scores are z-normalised per user. Titles the CF model cannot know (too new for
    the rating data) are scored by content alone, scaled by cold_scale so they can reach
    the top of the ranking without crowding out everything CF is confident about.
    """

    def __init__(self, cf, content, known, weight=0.8, cold_scale=1.3):
        self.cf, self.content, self.known, self.weight, self.cold_scale = cf, content, known, weight, cold_scale
        self.name = f"Hybrid ({cf.name})"

    def score(self, items, weights):
        c, f = self.content.score(items, weights), self.cf.score(items, weights)
        z = (c - c.mean()) / (c.std() + 1e-9)
        k = self.known
        s = f[k].std()
        zf = np.where(k, (f - f[k].mean()) / (s + 1e-9), 0.0)
        return np.where(k, self.weight * zf + (1 - self.weight) * z, self.cold_scale * z)
