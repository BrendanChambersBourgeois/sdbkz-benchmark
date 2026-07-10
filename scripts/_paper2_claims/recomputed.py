#!/usr/bin/env python3
"""Paper-2 claims ledger — RECOMPUTED slice (deep-audit finding 6, plan step 2).

Rebuilds two families of paper-2 numbers directly from the committed seed tree,
importing the EXISTING scoring primitives from ``scripts/extract_dsd_onset.py``
(``onset_for``, ``_seed_fires``) so the ledger is byte-identical to the
figure/table path rather than a reimplementation:

  (1) All DSD onsets + SD-vs-BKZ gap% for n in {89,101,113}, engine in
      {fplll,g6k}, variant in {sdbkz,bkz}   -> onset_for(...)
  (2) McNemar discordant counts (b:c) + chi2 and the exact sign-test p at the
      two transition cells (n=101 q=271, n=113 q=487, both engines).

Pure-python (exact binomial via math.comb) — no scipy dependency, so the
eventual builder inherits none. Read-only on results/seeds/.

build_records() -> list[dict], each dict = the ledger record schema:
  {claim_id, tex_lines, verbatim, paper_value, source, method,
   recomputed_value, match, status, note}
"""
from __future__ import annotations

import glob
import json
import os
import sys
from math import comb

# --- locate the repo and import the committed scoring primitives ------------
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (scripts/_paper2_claims/ -> up 3)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from extract_dsd_onset import _seed_fires, onset_for  # noqa: E402

ENGINE_TREE = {"fplll": "ntru", "g6k": "ntru_g6k"}
BETA = 40
RATE = 0.5

# ---------------------------------------------------------------------------
# Paper values (plan section 2.2 / 2.3 table; tex = paper2/latex/sdbkz_paper2.tex)
# ---------------------------------------------------------------------------
# onset[(n, engine)] = (sd, bkz, gap_pct, tex_lines)
ONSET_PAPER = {
    (89, "fplll"): (193.7, 193.8, 0, [560, 561, 562, 586]),
    (89, "g6k"):   (193.1, 194.0, 0, [560, 561, 563, 586]),
    (101, "fplll"): (257.3, 280.7, 9, [634, 661, 793]),
    (101, "g6k"):   (249.9, 268.3, 7, [634, 662, 793]),
    (113, "fplll"): (464.6, 499.0, 7, [643, 663]),
    (113, "g6k"):   (456.3, 482.2, 6, [644, 664]),
}

# transition[(n, engine)] = (q, b_paper, c_paper, chi2_paper, p_paper, p_sided, tex_lines)
#   p_paper is None where the tex cites only the count+chi2 (fplll n=101).
#   p_sided records which sign-test convention the tex actually used for the
#   cited p — the paper is INTERNALLY INCONSISTENT: g6k n=101 cites the
#   two-sided p, but fplll/g6k n=113 cite the one-sided p (see plan 2.3 and
#   the note on each record).
TRANSITION_PAPER = {
    (101, "fplll"): (271, 24, 1, 21.16, None, None, [636, 637, 638, 661]),
    (101, "g6k"):   (271, 17, 0, 17.0, 1.5e-5, "two-sided", [636, 662]),
    (113, "fplll"): (487, 19, 0, 19.0, 1.9e-6, "one-sided", [645, 646, 647, 648, 663]),
    (113, "g6k"):   (487, 14, 0, 14.0, 6.1e-5, "one-sided", [645, 664]),
}


# ---------------------------------------------------------------------------
# recompute helpers
# ---------------------------------------------------------------------------
def _recompute_onsets(n: int, engine: str):
    """(sd_onset, bkz_onset, gap_pct) via the committed onset_for path."""
    tree = ENGINE_TREE[engine]
    sd, _, _ = onset_for(tree, n, BETA, "sdbkz", RATE)
    bkz, _, _ = onset_for(tree, n, BETA, "bkz", RATE)
    gap = round(100.0 * (bkz - sd) / sd) if sd and bkz else None
    return sd, bkz, gap


def _cell_files(tree: str, n: int, beta: int, q: int):
    pat = os.path.join(REPO, "results", "seeds", tree, f"q{q}",
                       "p*_mt*", f"n{n:03d}_beta{beta:02d}", "seed*.json")
    return sorted(glob.glob(pat))


def _discordant(tree: str, n: int, q: int):
    """(b, c, N) discordant McNemar counts at one transition cell.
    b = SD-BKZ fires but BKZ does not; c = BKZ fires but SD-BKZ does not."""
    b = c = N = 0
    for f in _cell_files(tree, n, BETA, q):
        s = json.load(open(f))
        sd = _seed_fires(s, "sdbkz", n)
        bk = _seed_fires(s, "bkz", n)
        if sd and not bk:
            b += 1
        elif bk and not sd:
            c += 1
        N += 1
    return b, c, N


def _chi2(b: int, c: int) -> float:
    return (b - c) ** 2 / (b + c) if (b + c) else 0.0


def _sign_p_two_sided(b: int, c: int) -> float:
    """Exact two-sided sign-test p (task-specified formula, pure python)."""
    k, m = b + c, min(b, c)
    return 2 * sum(comb(k, i) for i in range(m + 1)) / 2 ** k


def _sign_p_one_sided(b: int, c: int) -> float:
    k, m = b + c, min(b, c)
    return sum(comb(k, i) for i in range(m + 1)) / 2 ** k


def _approx(a, b, rtol=5e-2) -> bool:
    """Relative match to ~2 sig figs (for p-values)."""
    if a == 0 or b == 0:
        return a == b
    return abs(a - b) / abs(b) <= rtol


# ---------------------------------------------------------------------------
# ledger builder
# ---------------------------------------------------------------------------
def build_records() -> list[dict]:
    records: list[dict] = []

    # (1) onsets + gap% -----------------------------------------------------
    for (n, engine), (sd_p, bkz_p, gap_p, tex) in sorted(ONSET_PAPER.items()):
        tree = ENGINE_TREE[engine]
        sd_r, bkz_r, gap_r = _recompute_onsets(n, engine)
        src = {"kind": "seeds",
               "glob": f"results/seeds/{tree}/q*/p*_mt50/n{n:03d}_beta{BETA:02d}/"}
        for variant, paper, recomputed in (("sdbkz", sd_p, sd_r),
                                           ("bkz", bkz_p, bkz_r)):
            match = recomputed is not None and abs(recomputed - paper) <= 0.1
            records.append({
                "claim_id": f"onset_n{n}_{engine}_{'sd' if variant == 'sdbkz' else 'bkz'}",
                "tex_lines": tex,
                "verbatim": f"{engine} SD {sd_p} / BKZ {bkz_p}"
                            + (f" ({gap_p}% gap)" if gap_p else " (null window)"),
                "paper_value": paper,
                "source": src,
                "method": f"extract_dsd_onset.onset_for(tree='{tree}', n={n}, "
                          f"beta={BETA}, variant='{variant}', rate={RATE})",
                "recomputed_value": recomputed,
                "match": match,
                "status": "RECOMPUTED" if match else "DERIVED-UNRESOLVED",
                "note": "50%-DSD-rate onset, linearly interpolated between "
                        "bracketing q-cells; byte-identical to the CLI / figure path.",
            })
        # gap% record for the cell
        gmatch = gap_r is not None and gap_r == gap_p
        records.append({
            "claim_id": f"gap_n{n}_{engine}",
            "tex_lines": tex,
            "verbatim": f"{engine} n={n}: {gap_p}% SD-vs-BKZ onset gap"
                        + (" (null / dense window)" if gap_p == 0 else ""),
            "paper_value": gap_p,
            "source": src,
            "method": f"round(100*(bkz_onset-sd_onset)/sd_onset) for n={n} {engine}",
            "recomputed_value": gap_r,
            "match": gmatch,
            "status": "RECOMPUTED" if gmatch else "DERIVED-UNRESOLVED",
            "note": "gap% derived from the two recomputed onsets above.",
        })

    # (2) McNemar counts + chi2 + sign-test p -------------------------------
    for (n, engine), (q, b_p, c_p, chi2_p, p_p, p_sided, tex) in sorted(
            TRANSITION_PAPER.items()):
        tree = ENGINE_TREE[engine]
        b_r, c_r, N = _discordant(tree, n, q)
        chi2_r = _chi2(b_r, c_r)
        src = {"kind": "seeds",
               "glob": f"results/seeds/{tree}/q{q}/p*_mt50/n{n:03d}_beta{BETA:02d}/"}

        # 2a. discordant counts b:c (exact string match)
        cnt_match = (b_r == b_p and c_r == c_p)
        records.append({
            "claim_id": f"mcnemar_counts_n{n}_{engine}",
            "tex_lines": tex,
            "verbatim": f"{engine} n={n} transition (q={q}): {b_p}:{c_p} discordant",
            "paper_value": f"{b_p}:{c_p}",
            "source": src,
            "method": f"per-seed _seed_fires vectors at q={q}; "
                      f"b=#(SD-only), c=#(BKZ-only) over N={N} seeds",
            "recomputed_value": f"{b_r}:{c_r}",
            "match": cnt_match,
            "status": "RECOMPUTED" if cnt_match else "DERIVED-UNRESOLVED",
            "note": f"N={N} seeds in the transition cell.",
        })

        # 2b. McNemar chi2 (no continuity correction)
        chi2_match = _approx(chi2_r, chi2_p, rtol=5e-3)
        records.append({
            "claim_id": f"mcnemar_chi2_n{n}_{engine}",
            "tex_lines": tex,
            "verbatim": f"{engine} n={n} transition (q={q}): chi2={chi2_p}",
            "paper_value": chi2_p,
            "source": src,
            "method": "(b-c)^2/(b+c) from the recomputed discordant counts",
            "recomputed_value": round(chi2_r, 2),
            "match": chi2_match,
            "status": "RECOMPUTED" if chi2_match else "DERIVED-UNRESOLVED",
            "note": "McNemar chi-square, no continuity correction.",
        })

        # 2c. exact sign-test p (only where the tex cites one)
        if p_p is not None:
            two = _sign_p_two_sided(b_r, c_r)
            one = _sign_p_one_sided(b_r, c_r)
            # The tex value matches whichever convention p_sided names; the
            # task-specified formula is the TWO-sided one. We report the value
            # under the paper's own convention and flag the inconsistency.
            recomputed = two if p_sided == "two-sided" else one
            pmatch = _approx(recomputed, p_p, rtol=5e-2)
            note = (f"Exact binomial sign-test. Paper cites the {p_sided} p. "
                    f"two-sided={two:.3e}, one-sided={one:.3e}. "
                    "PAPER SIDEDNESS INCONSISTENCY: g6k n=101 cites two-sided "
                    "(1.5e-5) while n=113 (fplll/g6k) cite one-sided "
                    "(1.9e-6/6.1e-5); the task-specified two-sided formula alone "
                    "only reproduces g6k n=101.")
            records.append({
                "claim_id": f"signtest_p_n{n}_{engine}",
                "tex_lines": tex,
                "verbatim": f"{engine} n={n} transition (q={q}): sign p~={p_p:.1e} ({p_sided})",
                "paper_value": p_p,
                "source": src,
                "method": ("exact sign-test on all-one-direction discordants: "
                           f"{p_sided}; two-sided=2*sum(comb(b+c,i),i<=min(b,c))/2**(b+c)"),
                "recomputed_value": recomputed,
                "match": pmatch,
                "status": "RECOMPUTED" if pmatch else "DERIVED-UNRESOLVED",
                "note": note,
            })

    return records


if __name__ == "__main__":
    recs = build_records()
    allmatch = all(r["match"] for r in recs)
    for r in recs:
        flag = "OK " if r["match"] else "XX "
        print(f"{flag}{r['claim_id']:28} paper={r['paper_value']!s:10} "
              f"recomp={r['recomputed_value']!s:10} [{r['status']}]")
    print(f"\n{sum(r['match'] for r in recs)}/{len(recs)} match; "
          f"all_reproduced={allmatch}")
