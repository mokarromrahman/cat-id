"""Train the cat classifier.

Layout:  data/<class_name>/*.jpg   (e.g. data/Litten, data/Shinx, data/neither)
Output:  model.joblib  (classifier + class names)
"""
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from embed import embed, open_image

DATA = Path("data")
CACHE = Path("embeddings_cache.npz")
EXTS = {".jpg", ".jpeg", ".png", ".webp"}
BATCH = 16


def collect():
    items = []
    for cls_dir in sorted(p for p in DATA.iterdir() if p.is_dir()):
        for f in sorted(cls_dir.iterdir()):
            if f.suffix.lower() in EXTS:
                items.append((str(f), cls_dir.name))
    return items


def main():
    items = collect()
    if not items:
        sys.exit("No images found under data/<class>/")

    # Reuse cached embeddings so retraining after adding photos is fast.
    cache = {}
    if CACHE.exists():
        z = np.load(CACHE, allow_pickle=True)
        cache = dict(zip(z["paths"].tolist(), z["vecs"]))

    todo = [p for p, _ in items if p not in cache]
    print(f"{len(items)} images, {len(todo)} new to embed")
    for i in range(0, len(todo), BATCH):
        chunk = todo[i : i + BATCH]
        vecs = embed([open_image(p) for p in chunk])
        for p, v in zip(chunk, vecs):
            cache[p] = v
        print(f"  embedded {min(i + BATCH, len(todo))}/{len(todo)}", flush=True)
    np.savez(CACHE, paths=np.array(list(cache.keys())), vecs=np.stack(list(cache.values())))

    X = np.stack([cache[p] for p, _ in items])
    y = np.array([c for _, c in items])
    classes, counts = np.unique(y, return_counts=True)
    print("classes:", dict(zip(classes, counts)))

    clf = LogisticRegression(C=10, max_iter=3000, class_weight="balanced")

    # Honest estimate. Caveat: random folds can leak near-duplicate burst shots,
    # so treat this as an optimistic upper bound.
    if counts.min() >= 5:
        pred = cross_val_predict(clf, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0))
        print(classification_report(y, pred, digits=3))

    clf.fit(X, y)
    joblib.dump({"clf": clf, "classes": clf.classes_.tolist()}, "model.joblib")
    print("saved model.joblib")


if __name__ == "__main__":
    main()
