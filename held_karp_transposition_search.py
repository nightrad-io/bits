"""
Usage: python3 held_karp_transposition_search.py [col_width] [row|col] [--selftest]
  col_width   default 22
  row|col     edge-weight convention, default row
  --selftest  verify Held-Karp reproduces the known exhaustive optimum
              at col_width=8 (col convention) before running the real search
"""

import sys, time, array, math
from body_key_transposition_search import (
    body_seq, key_seq, PATTERNS, bigram_or_zero,
)

# Trigram scoring: used as the DEFAULT reported/ranking metric (which
# variant counts as "best", what score gets printed), NOT as the Held-Karp
# search objective. Trigrams are far more discriminating than bigrams
# (7,450 distinct trigrams vs. 576 possible bigrams -- closer to real
# word-fragment structure), which matters for telling a genuine signal
# apart from a bigram-favorable false positive. But making trigrams the
# SEARCH objective would require the DP state to track the last TWO
# columns instead of one (dp[mask][prev2][prev1] instead of
# dp[mask][last]), multiplying both time and memory by ~n (~22x at
# n=22 -- ~90s/variant becomes ~33min/variant, ~830MB becomes ~18GB).
# So the search itself stays on the cheap bigram edge weights; trigram
# scoring is applied once, cheaply (O(length)), to the ALREADY-DECODED
# text each variant's Held-Karp run produces.
_trigram_counts = {}
_trigram_total = 0.0
with open('trigram_model.txt') as f:
    for line in f:
        tg, c = line.strip().split('\t')
        _trigram_counts[tg] = float(c)
        _trigram_total += float(c)
_TRI_FLOOR = 1e-7
_trigram_logprob = {}  # filled lazily per-trigram below (7450 entries isn't worth precomputing 24^3)

def trigram_score(text):
    """Sum of trigram log-probabilities over a decoded string. Trigrams
    touching the '.' padding/separator character are skipped."""
    total = 0.0
    for i in range(len(text) - 2):
        tg = text[i:i+3]
        if '.' in tg:
            continue
        lp = _trigram_logprob.get(tg)
        if lp is None:
            p = _trigram_counts.get(tg, 0.0) / _trigram_total
            lp = math.log(max(p, _TRI_FLOOR))
            _trigram_logprob[tg] = lp
        total += lp
    return total

ALPHA24 = 'ABCDEFGHJKLMNOPQRSTVWXYZ'  # this cipher's merged 24-letter alphabet (no I or U)
_ALPHA24_IDX = {c: i for i, c in enumerate(ALPHA24)}

def shift_letters(letters, s):
    """Caesar-shift a list of single-char letters by s positions on the
    24-letter merged alphabet (motivated by the chi2 letter-frequency
    finding: shifting body=alt-fwd/key=alt-rev by 1 dropped chi2 from
    786.1 to 62.0, validated at z=-2.03 against a shuffled-label null --
    see conversation. Doesn't change which letters are present in what
    RELATIVE proportion, just relabels them, so it can turn an
    English-shaped-but-wrong-alphabet frequency profile into a
    genuinely English one.)"""
    if s == 0:
        return letters
    return [ALPHA24[(_ALPHA24_IDX[c] + s) % 24] for c in letters]

def build_grid(body_letters, key_letters, col_width, col_major):
    combined = body_letters + ['.'] + key_letters  # 88 chars, dot at body/key boundary
    if len(combined) % col_width != 0:
        pad = col_width - (len(combined) % col_width)
        combined = combined + ['.'] * pad
    nrows = len(combined) // col_width
    grid = [[None] * col_width for _ in range(nrows)]
    idx = 0
    if col_major:
        for c in range(col_width):
            for r in range(nrows):
                grid[r][c] = combined[idx]; idx += 1
    else:
        for r in range(nrows):
            for c in range(col_width):
                grid[r][c] = combined[idx]; idx += 1
    return grid, nrows

def edge_weights_row_major(grid, nrows, col_width, btt):
    row_order = list(range(nrows - 1, -1, -1)) if btt else list(range(nrows))
    W = [[0.0] * col_width for _ in range(col_width)]
    for i in range(col_width):
        for j in range(col_width):
            if i == j:
                continue
            s = 0.0
            for r in row_order:
                s += bigram_or_zero(grid[r][i], grid[r][j])
            W[i][j] = s
    return W, row_order

def edge_weights_col_major(grid, nrows, col_width, btt):
    row_range = list(range(nrows - 1, -1, -1)) if btt else list(range(nrows))
    first_char = [grid[row_range[0]][c] for c in range(col_width)]
    last_char = [grid[row_range[-1]][c] for c in range(col_width)]
    W = [[0.0] * col_width for _ in range(col_width)]
    for i in range(col_width):
        for j in range(col_width):
            if i == j:
                continue
            W[i][j] = bigram_or_zero(last_char[i], first_char[j])
    return W, first_char, last_char

def format_grid_view(grid, order, nrows):
    """The reordered grid, one row per line -- makes row membership (e.g.
    where the '.' body/key boundary lands) directly visible, instead of
    burying it inside a single flattened text string with no visible row
    breaks. For row-major convention this is exactly what the flat text is
    built from (its rows, concatenated); for column-major it's still a
    correct, useful view of the reordered grid even though that
    convention's flat text is built by column-chunks instead."""
    return [''.join(grid[r][c] for c in order) for r in range(nrows)]

def held_karp(W, n):
    """Exact max-weight Hamiltonian path, free start/end. Returns (score, order)."""
    size = 1 << n
    NEG = float('-inf')
    dp = array.array('d', [NEG]) * (size * n)
    bp = array.array('b', [-1]) * (size * n)

    for i in range(n):
        dp[(1 << i) * n + i] = 0.0

    for mask in range(1, size):
        base_row = mask * n
        # collect valid i's for this mask cheaply
        for i in range(n):
            if not (mask & (1 << i)):
                continue
            cur = dp[base_row + i]
            if cur == NEG:
                continue
            Wi = W[i]
            for j in range(n):
                bit = 1 << j
                if mask & bit:
                    continue
                cand = cur + Wi[j]
                idx = (mask | bit) * n + j
                if cand > dp[idx]:
                    dp[idx] = cand
                    bp[idx] = i

    full = size - 1
    base_row = full * n
    best_j = max(range(n), key=lambda j: dp[base_row + j])
    best_score = dp[base_row + best_j]

    order = []
    mask = full
    j = best_j
    while j != -1:
        order.append(j)
        idx = mask * n + j
        pj = bp[idx]
        mask ^= (1 << j)
        j = pj
    order.reverse()
    return best_score, order

def selftest():
    """Verify Held-Karp (col-major convention) matches the known exhaustive
    optimum at col_width=8 from body_key_transposition_search.py."""
    from body_key_transposition_search import build_variant, exact_search
    body_letters = PATTERNS['1,2,3'](body_seq)
    key_letters = PATTERNS['1,2,3'](key_seq)
    col_chars, first_char, last_char, intra_total, nrows = build_variant(
        body_letters, key_letters, 8, False, False)
    exhaustive_score, exhaustive_order = exact_search(col_chars, first_char, last_char, intra_total, 8)

    grid, nrows2 = build_grid(body_letters, key_letters, 8, False)
    W, fc, lc = edge_weights_col_major(grid, nrows2, 8, False)
    hk_score_edges_only, hk_order = held_karp(W, 8)
    hk_score_full = hk_score_edges_only + intra_total

    print(f"Exhaustive (body_key_transposition_search.py): score={exhaustive_score:.4f}  order={exhaustive_order}")
    print(f"Held-Karp (edges only {hk_score_edges_only:.4f} + intra_total {intra_total:.4f} = {hk_score_full:.4f})  order={hk_order}")
    ok = abs(hk_score_full - exhaustive_score) < 1e-6
    print("MATCH" if ok else "MISMATCH -- bug!", flush=True)
    return ok

def main():
    argv = sys.argv[1:]
    shift = 0
    if '--shift' in argv:
        i = argv.index('--shift')
        shift = int(argv[i+1])
        argv = argv[:i] + argv[i+2:]  # strip so positional parsing below is unaffected
    args = [a for a in argv if not a.startswith('--')]
    flags = [a for a in argv if a.startswith('--')]

    if '--selftest' in flags:
        ok = selftest()
        if not ok:
            sys.exit(1)
        print()

    col_width = int(args[0]) if len(args) > 0 else 22
    convention = args[1] if len(args) > 1 else 'row'
    assert convention in ('row', 'col')

    # fill=row (text packed across each row before the next) is the
    # default now -- fill=col (packed down each column first) is a
    # SEPARATE grid layout, not a variation reachable by column
    # reordering of the same one, so it's opt-in via --fill-col.
    fill_options = (False, True) if '--fill-col' in flags else (False,)

    # btt (row-traversal direction) is a mathematical no-op for row-major
    # edge weights: W[i][j] = sum over ALL rows of bigram(grid[r][i],
    # grid[r][j]), and addition is commutative, so reversing which order
    # the rows are summed in never changes the total (row-wrap junction
    # bigrams would depend on direction, but those are deliberately not
    # part of the Held-Karp objective -- see module docstring). Column-
    # major scoring genuinely depends on btt (it changes which row is
    # "first"/"last" per column), so only row-major skips the redundant half.
    btt_options = (False,) if convention == 'row' else (False, True)
    total_variants = len(PATTERNS) * len(PATTERNS) * len(fill_options) * len(btt_options)

    print(f"Column width: {col_width}   Convention: {'row-major (aggregated)' if convention=='row' else 'column-major (single boundary bigram)'}")
    if shift:
        print(f"Caesar shift: +{shift} (24-letter alphabet) applied to body and key letters before gridding")
    print(f"Fill: {'row only (pass --fill-col to also test fill=col)' if fill_options==(False,) else 'row and col'}")
    print(f"State space: 2^{col_width} x {col_width} = {(1<<col_width)*col_width:,} dp cells")
    if convention == 'row':
        print(f"Note: read-direction (btt) is a no-op for row-major scoring -- skipping it, "
              f"{total_variants} variants instead of {total_variants*2}\n")
    else:
        print()

    best_overall = None
    t0 = time.time()
    variant_count = 0
    for bname, bfn in PATTERNS.items():
        body_letters = shift_letters(bfn(body_seq), shift)
        for kname, kfn in PATTERNS.items():
            key_letters = shift_letters(kfn(key_seq), shift)
            for col_major in fill_options:
                for btt in btt_options:
                    variant_count += 1
                    label = (f"body={bname} key={kname} fill={'col' if col_major else 'row'} "
                             f"read={'bottom' if btt else 'top'}")
                    grid, nrows = build_grid(body_letters, key_letters, col_width, col_major)
                    vt0 = time.time()
                    if convention == 'row':
                        W, row_order = edge_weights_row_major(grid, nrows, col_width, btt)
                    else:
                        W, fc, lc = edge_weights_col_major(grid, nrows, col_width, btt)
                    bi_score, order = held_karp(W, col_width)  # search objective (unchanged, fast)
                    vt1 = time.time()

                    text = ''.join(''.join(grid[r][c] for c in order) for r in range(nrows)) if convention == 'row' \
                           else ''.join(''.join(grid[r][c] for r in range(nrows)) for c in order)
                    tri_score = trigram_score(text)  # default reported/ranking metric

                    if best_overall is None or tri_score > best_overall[0]:
                        best_overall = (tri_score, bi_score, order, label, text, grid, nrows)
                        print(f"[{time.time()-t0:7.1f}s] variant {variant_count}/{total_variants} ({vt1-vt0:.1f}s)  "
                              f"NEW BEST tri={tri_score:.2f} (bi={bi_score:.2f})  [{label}]", flush=True)
                        print(f"           column order: {order}")
                        for r, row in enumerate(format_grid_view(grid, order, nrows)):
                            marker = '  <-- dot' if '.' in row else ''
                            print(f"           row {r}: {row}{marker}")
                        print(f"           text (rows concatenated): {text}\n", flush=True)
                    else:
                        print(f"[{time.time()-t0:7.1f}s] variant {variant_count}/{total_variants} ({vt1-vt0:.1f}s)  "
                              f"tri={tri_score:.2f} (bi={bi_score:.2f})  [{label}]", flush=True)

    elapsed = time.time() - t0
    print(f"\nDone. {variant_count} variants in {elapsed:.1f}s.")
    tri_score, bi_score, order, label, text, grid, nrows = best_overall
    print(f"Global best: tri={tri_score:.2f} (bi={bi_score:.2f})  [{label}]")
    print(f"column order: {order}")
    for r, row in enumerate(format_grid_view(grid, order, nrows)):
        marker = '  <-- dot' if '.' in row else ''
        print(f"row {r}: {row}{marker}")
    print(f"text (rows concatenated): {text}")

if __name__ == '__main__':
    main()
