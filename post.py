"""
eda_post.py  —  Post-embedding analysis
========================================
Run AFTER build_index.py.

Tests:
  1. Intra vs inter-brand similarity
  2. Nearest-neighbour brand purity
  3. Cross-brand confusion matrix
  4. TTA vs no-TTA accuracy on test images
  5. UMAP 2D plot coloured by brand (requires: pip install umap-learn matplotlib)

Output:

Usage:
  python eda_post.py
  python eda_post.py --no-umap     # skip UMAP (faster, no extra dependencies)
  python eda_post.py --test-images # also run TTA vs no-TTA on test set
"""

import argparse, json, time
import numpy as np
from collections import defaultdict, Counter
from pathlib import Path

BASE_DIR     = Path(r"C:\Misc_progs\RO\ro_v2")
EDA_DIR      = BASE_DIR / "eda"
EDA_DIR.mkdir(exist_ok=True)
VECTORS_PATH = BASE_DIR / "clip_vectors.npy"
INDEX_PATH   = BASE_DIR / "clip_index.json"
REPORT       = EDA_DIR  / "eda_post_report.txt"

TEST_IMAGES = [
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\5e9e88fb1a18.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\4e490a5df677.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\ef0c47d18e17.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\fb888694eab5.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\b84050da12fd.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\1e29797e22b3.jpg",
    r"C:\Misc_progs\RO\ro_catalogue\ro_catalogue\images\3c57744eb37e.jpg",
]

lines = []
def log(s=""):
    print(s)
    lines.append(s)

# ── Load index ────────────────────────────────────────────────────────
def load():
    if not VECTORS_PATH.exists():
        raise FileNotFoundError(f"Run build_index.py first. Missing: {VECTORS_PATH}")
    vectors = np.load(str(VECTORS_PATH))
    index   = json.loads(INDEX_PATH.read_text())
    return vectors, index

# ── 1. Intra vs inter-brand similarity ───────────────────────────────
def analyse_brand_similarity(vectors, index):
    log("─" * 60)
    log("1. INTRA vs INTER-BRAND COSINE SIMILARITY")
    log("─" * 60)

    brands     = [e["brand"] for e in index]
    brand_set  = sorted(set(brands))

    # Full similarity matrix (N x N dot product, vectors already normalised)
    # For large N, sample instead — but at ~200 products it's fine
    sim_matrix = vectors @ vectors.T   # [N, N]
    np.fill_diagonal(sim_matrix, np.nan)  # exclude self

    intra_sims = []
    inter_sims = []

    for i in range(len(index)):
        for j in range(i + 1, len(index)):
            s = sim_matrix[i, j]
            if np.isnan(s):
                continue
            if brands[i] == brands[j]:
                intra_sims.append(s)
            else:
                inter_sims.append(s)

    log(f"\n  Intra-brand (same brand)  : "
        f"mean={np.mean(intra_sims):.4f}  "
        f"min={np.min(intra_sims):.4f}  "
        f"max={np.max(intra_sims):.4f}")
    log(f"  Inter-brand (diff brand)  : "
        f"mean={np.mean(inter_sims):.4f}  "
        f"min={np.min(inter_sims):.4f}  "
        f"max={np.max(inter_sims):.4f}")

    ratio = np.mean(intra_sims) / np.mean(inter_sims)
    log(f"\n  Ratio intra/inter         : {ratio:.4f}")

    if ratio > 1.05:
        log(f"  ✓ Good — CLIP separates brands (ratio > 1.05)")
    elif ratio > 1.01:
        log(f"  ~ Marginal — slight brand separation (ratio 1.01-1.05)")
    else:
        log(f"  ✗ Poor — brands not well separated (ratio ≤ 1.01)")
        log(f"    → Consider fine-tuning or using a larger CLIP model")

    # Per-brand intra similarity
    log(f"\n  Per-brand intra similarity:")
    log(f"  {'Brand':<20} {'N':>4} {'Mean':>7} {'Min':>7} {'Max':>7}")
    log(f"  {'─'*20} {'─'*4} {'─'*7} {'─'*7} {'─'*7}")
    for brand in brand_set:
        idxs = [i for i, b in enumerate(brands) if b == brand]
        if len(idxs) < 2:
            log(f"  {brand:<20} {len(idxs):>4}  (only 1 product, skip)")
            continue
        sims = [sim_matrix[i, j]
                for ii, i in enumerate(idxs)
                for j in idxs[ii+1:]
                if not np.isnan(sim_matrix[i,j])]
        if not sims:
            continue
        log(f"  {brand:<20} {len(idxs):>4} {np.mean(sims):>7.4f} "
            f"{np.min(sims):>7.4f} {np.max(sims):>7.4f}")

    return sim_matrix, brands

# ── 2. Nearest-neighbour brand purity ─────────────────────────────────
def nn_brand_purity(vectors, index, sim_matrix, brands, K=5):
    log("\n" + "─" * 60)
    log(f"2. NEAREST-NEIGHBOUR BRAND PURITY  (K={K})")
    log("─" * 60)

    brand_set     = sorted(set(brands))
    purity_scores = []
    brand_purity  = defaultdict(list)

    for i in range(len(index)):
        row      = sim_matrix[i].copy()
        row[i]   = -np.inf                         # exclude self
        top_k    = np.argsort(row)[::-1][:K]
        same     = sum(1 for j in top_k if brands[j] == brands[i])
        purity   = same / K
        purity_scores.append(purity)
        brand_purity[brands[i]].append(purity)

    overall = np.mean(purity_scores)
    log(f"\n  Overall NN brand purity (K={K}): {overall:.3f}  "
        f"({overall*100:.0f}% of neighbours are same brand)")

    if overall >= 0.6:
        log(f"  ✓ Good purity (≥60%)")
    elif overall >= 0.4:
        log(f"  ~ Moderate purity (40-60%) — search may confuse brands")
    else:
        log(f"  ✗ Low purity (<40%) — significant brand confusion expected")

    log(f"\n  {'Brand':<20} {'N':>4} {'Purity':>8}")
    log(f"  {'─'*20} {'─'*4} {'─'*8}")
    for brand in brand_set:
        scores = brand_purity[brand]
        if not scores:
            continue
        avg = np.mean(scores)
        bar = "█" * int(avg * 10)
        log(f"  {brand:<20} {len(scores):>4} {avg:>7.3f}  {bar}")

    # Find worst-purity products (most confused)
    log(f"\n  Most confused products (lowest NN purity):")
    sorted_idx = np.argsort(purity_scores)
    for i in sorted_idx[:8]:
        entry = index[i]
        row   = sim_matrix[i].copy()
        row[i] = -np.inf
        top5  = np.argsort(row)[::-1][:5]
        nn_brands = Counter(brands[j] for j in top5)
        log(f"  [{entry['brand']:<15}] {entry['full_name'][:40]}")
        log(f"    purity={purity_scores[i]:.2f}  "
            f"NN brands: {dict(nn_brands.most_common(3))}")

    return purity_scores

# ── 3. Cross-brand confusion matrix ───────────────────────────────────
def confusion_matrix(vectors, index, sim_matrix, brands):
    log("\n" + "─" * 60)
    log("3. CROSS-BRAND CONFUSION MATRIX  (top-1 NN)")
    log("─" * 60)

    brand_set = sorted(set(brands))
    b2i       = {b: i for i, b in enumerate(brand_set)}
    n         = len(brand_set)
    matrix    = np.zeros((n, n), dtype=int)

    for i in range(len(index)):
        row     = sim_matrix[i].copy()
        row[i]  = -np.inf
        top1    = int(np.argmax(row))
        true_b  = brands[i]
        pred_b  = brands[top1]
        matrix[b2i[true_b], b2i[pred_b]] += 1

    # Print matrix
    log(f"\n  Rows = true brand, Cols = top-1 NN brand")
    log(f"  Diagonal = correctly retrieved same-brand neighbour\n")
    header = "  " + " " * 18
    for b in brand_set:
        header += f"{b[:6]:>7}"
    log(header)
    log("  " + "─" * (18 + 7 * len(brand_set)))
    for i, b in enumerate(brand_set):
        row_str = f"  {b:<18}"
        for j in range(n):
            val = matrix[i, j]
            marker = f"[{val:>3}]" if i == j else f" {val:>4} "
            row_str += marker
        log(row_str)

    # Top off-diagonal confusions
    log(f"\n  Top cross-brand confusions:")
    off_diag = []
    for i in range(n):
        for j in range(n):
            if i != j and matrix[i, j] > 0:
                off_diag.append((matrix[i, j], brand_set[i], brand_set[j]))
    off_diag.sort(reverse=True)
    for count, true_b, pred_b in off_diag[:8]:
        log(f"    {true_b:<15} → {pred_b:<15}  ({count} times)")

# ── 4. TTA vs no-TTA on test images ───────────────────────────────────
def tta_comparison(vectors, index):
    log("\n" + "─" * 60)
    log("4. TTA vs NO-TTA COMPARISON")
    log("─" * 60)

    try:
        from search import encode_single, augmented_query_vector
        from PIL import Image
    except ImportError:
        log("  Skipped — run from same directory as search.py")
        return

    existing = [p for p in TEST_IMAGES if Path(p).exists()]
    if not existing:
        log("  No test images found — update TEST_IMAGES paths")
        return

    log(f"\n  Testing {len(existing)} images\n")
    log(f"  {'Image':<25} {'No-TTA top1':>25} {'TTA top1':>25} {'Same?':>6}")
    log(f"  {'─'*25} {'─'*25} {'─'*25} {'─'*6}")

    for img_path in existing:
        img  = Image.open(img_path).convert("RGB")
        name = Path(img_path).stem[:22]

        # No TTA
        v_plain  = encode_single(img)
        s_plain  = vectors @ v_plain
        top_plain = index[int(np.argmax(s_plain))]

        # TTA
        v_tta   = augmented_query_vector(img)
        s_tta   = vectors @ v_tta
        top_tta = index[int(np.argmax(s_tta))]

        same = "✓" if top_plain["id"] == top_tta["id"] else "✗"
        log(f"  {name:<25} "
            f"{top_plain['brand'][:10]+' '+top_plain['model'][:13]:>25} "
            f"{top_tta['brand'][:10]+' '+top_tta['model'][:13]:>25} "
            f"{same:>6}")

        # Score improvement
        plain_score = float(np.max(s_plain))
        tta_score   = float(np.max(s_tta))
        log(f"    scores: plain={plain_score:.4f}  tta={tta_score:.4f}"
            f"  Δ={tta_score-plain_score:+.4f}")

# ── 5. UMAP plot ──────────────────────────────────────────────────────
def umap_plot(vectors, index):
    log("\n" + "─" * 60)
    log("5. UMAP 2D VISUALISATION")
    log("─" * 60)

    try:
        import umap
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        log("  Skipped — install with: pip install umap-learn matplotlib")
        return

    log("  Running UMAP (may take 30-60s)...")
    reducer  = umap.UMAP(n_components=2, random_state=42,
                         n_neighbors=10, min_dist=0.1)
    embedding = reducer.fit_transform(vectors)

    brands    = [e["brand"]    for e in index]
    cats      = [e["category"] for e in index]

    brand_set = sorted(set(brands))
    cat_set   = sorted(set(cats))

    # Colour palettes
    brand_colors = plt.cm.tab20(np.linspace(0, 1, len(brand_set)))
    cat_colors   = plt.cm.Set1(np.linspace(0, 1, len(cat_set)))
    b2c = {b: brand_colors[i] for i, b in enumerate(brand_set)}
    c2c = {c: cat_colors[i]   for i, c in enumerate(cat_set)}

    for fname, color_map, label_set, title_suffix in [
        ("umap_brands.png",     b2c, brand_set, "by Brand"),
        ("umap_categories.png", c2c, cat_set,   "by Category"),
    ]:
        fig, ax = plt.subplots(figsize=(14, 10))

        if fname == "umap_brands.png":
            labels = brands
        else:
            labels = cats

        for label in label_set:
            mask = [i for i, l in enumerate(labels) if l == label]
            ax.scatter(embedding[mask, 0], embedding[mask, 1],
                       c=[color_map[label]], label=label,
                       s=60, alpha=0.8, edgecolors="white", linewidths=0.5)

        ax.set_title(f"CLIP Embeddings — RO Catalogue {title_suffix}",
                     fontsize=14, fontweight="bold")
        ax.set_xlabel("UMAP dim 1")
        ax.set_ylabel("UMAP dim 2")
        ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left",
                  fontsize=8, framealpha=0.9)
        ax.grid(True, alpha=0.2)
        plt.tight_layout()

        out = EDA_DIR / fname
        plt.savefig(str(out), dpi=150, bbox_inches="tight")
        plt.close()
        log(f"  Saved: {out}")

    log("\n  How to read the UMAP plots:")
    log("  ✓ Good: tight clusters per brand/category, minimal overlap")
    log("  ✗ Bad:  brands/categories mixed together throughout")

# ── Main ──────────────────────────────────────────────────────────────
def main(args):
    vectors, index = load()

    log("=" * 60)
    log("  EDA POST-EMBEDDING REPORT")
    log("=" * 60)
    log(f"\n  Vectors shape : {vectors.shape}")
    log(f"  Index entries : {len(index)}")
    log(f"  Brands        : {len(set(e['brand'] for e in index))}")
    log(f"  Categories    : {len(set(e['category'] for e in index))}")

    # Check normalisation
    norms = np.linalg.norm(vectors, axis=1)
    log(f"  L2 norm range : {norms.min():.4f} – {norms.max():.4f}"
        f"  (should be ~1.0)")

    brands = [e["brand"] for e in index]

    log("")
    sim_matrix, brands = analyse_brand_similarity(vectors, index)
    nn_brand_purity(vectors, index, sim_matrix, brands)
    confusion_matrix(vectors, index, sim_matrix, brands)

    if args.test_images:
        tta_comparison(vectors, index)

    if not args.no_umap:
        umap_plot(vectors, index)

    log("\n" + "=" * 60)
    log("SUMMARY")
    log("=" * 60)
    log(f"\n  Index size     : {len(index)} products")
    log(f"  Report saved   : {REPORT}")

    REPORT.write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-umap",      action="store_true",
                        help="Skip UMAP plot")
    parser.add_argument("--test-images",  action="store_true",
                        help="Run TTA vs no-TTA on test image set")
    main(parser.parse_args())