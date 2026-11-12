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
  (3) tab:dsdgap onsets (beta=20; flag and exact recovery) + flag gap%.
  (4) Per-key exact-recovery counts at beta=40 (n=89, 101, 113, both engines).
  (5) tab:dimonset mean advantage per n.

Pure-python (exact binomial via math.comb) — no scipy dependency, so the
eventual builder inherits none. Read-only on results/seeds/.

build_records() -> list[dict], each dict = the ledger record schema:
  {claim_id, tex_anchors, verbatim, paper_value, source, method,
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
from extract_dsd_onset import (  # noqa: E402
    DEFAULT_TOURS,
    _seed_fires,
    onset_for,
    report_cell,
)

ENGINE_TREE = {"fplll": "ntru", "g6k": "ntru_g6k"}
BETA = 40
RATE = 0.5

# ---------------------------------------------------------------------------
# Paper values (plan section 2.2 / 2.3 table; tex = paper2/latex/sdbkz_paper2.tex)
# ---------------------------------------------------------------------------
# onset[(n, engine)] = (sd, bkz, gap_pct, tex_anchors)
_N89 = r"& 193.7 & 193.8 & 193.1 & 194.0"
ONSET_PAPER = {
    (89, "fplll"): (193.7, 193.8, 0, [_N89]),
    (89, "g6k"):   (193.1, 194.0, 0, [_N89]),
    (101, "fplll"): (257.3, 280.7, 9, [r"101 & fplll & 257.3 & 280.7",
                                       r"recovers a $9\%$ SD$<$BKZ DSD-onset"]),
    (101, "g6k"):   (249.9, 268.3, 7, [r"101 & G6K   & 249.9 & 268.3",
                                       r"$[6.0\%,11.0\%]$) and $7\%$ on G6K"]),
    (113, "fplll"): (464.6, 499.0, 7, [r"113 & fplll & 464.6 & 499.0",
                                       r"($7\%$ gap fplll,"]),
    (113, "g6k"):   (456.3, 482.2, 6, [r"113 & G6K   & 456.3 & 482.2",
                                       r"$6\%$ G6K), and at $q=487$"]),
}

# transition[(n, engine)] = (q, b_paper, c_paper, chi2_paper, p_paper, p_sided, tex_anchors)
#   p_paper is None where the tex cites only the count+chi2 (fplll n=101).
#   All cited p are two-sided (n=113 was one-sided earlier).
_P113 = r"(sign test $p\approx3.8\times10^{-6}$ and $1.2\times10^{-4}$)"
TRANSITION_PAPER = {
    (101, "fplll"): (271, 24, 1, 21.2, None, None, [r"($24{:}1$, $\chi^2{=}21.2$)"]),
    (101, "g6k"):   (271, 17, 0, 17.0, 1.5e-5, "two-sided",
                     [r"($17{:}0$, $\chi^2{=}17.0$)",
                      r"two-sided sign test ($p\approx1.5\times10^{-5}$)"]),
    (113, "fplll"): (487, 19, 0, 19.0, 3.8e-6, "two-sided",
                     [r"($19{:}0$, $\chi^2{=}19.0$)", _P113]),
    (113, "g6k"):   (487, 14, 0, 14.0, 1.2e-4, "two-sided",
                     [r"($14{:}0$, $\chi^2{=}14.0$)", _P113]),
}

# tab:dsdgap (beta=20, fplll): (n, scoring) -> (sd, bkz, gap_pct or None, tex_anchors).
# flag = ntru tree (two-part criterion), skr = ntru_exact tree (exact recovery).
# The SKR gaps carry intervals and live in derived_numeric.
DSDGAP_BETA = 20
DSDGAP_TREE = {"flag": "ntru", "skr": "ntru_exact"}
DSDGAP_PAPER = {
    (67, "flag"): (144.6, 145.4, None, [r"67$^\ast$  & 144.6 & 145.4 & --"]),
    (79, "flag"): (171.2, 171.0, None, [r"79$^\ast$  & 171.2 & 171.0 & --"]),
    (89, "flag"): (238.0, 283.3, 19, [r"89  & 238.0 & 283.3 & 19 &",
                                      r"($19$--$28\%$ scored by a reference-free",
                                      r"above SD-BKZ's in $q$ at $n=89$ and $101$"]),
    (101, "flag"): (428.6, 512.2, 19, [r"101 & 428.6 & 512.2 & 19 &",
                                       r"above SD-BKZ's in $q$ at $n=89$ and $101$"]),
    (113, "flag"): (729.2, 930.4, 28, [r"113 & 729.2 & 930.4 & 28 &",
                                       r"($19$--$28\%$ scored by a reference-free",
                                       r"$28\%$ at $n=113$"]),
    (89, "skr"): (187.2, 224.3, None, [r"& 187.2 & 224.3 & 20 \\"]),
    (101, "skr"): (363.7, 469.7, None, [r"& 363.7 & 469.7 & 29 \\"]),
    (113, "skr"): (694.3, 854.5, None, [r"& 694.3 & 854.5 & 23 \\"]),
}

# Per-key exact recovery at beta=40: keys recovering in more q-cells under
# SD-BKZ : under BKZ. "unresolved" is the tex reading where no count is printed.
_LEADS = r"SD-BKZ leads per key at $n=89$ and $113$ on"
PER_KEY_TREE = {"fplll": "ntru_exact", "g6k": "ntru_g6k_exact"}
PER_KEY_PAPER = {
    (89, "fplll"): ("49:17", [r"($49{:}17$ fplll, $47{:}12$ G6K)", _LEADS]),
    (89, "g6k"): ("47:12", [r"($49{:}17$ fplll, $47{:}12$ G6K)", _LEADS]),
    (113, "fplll"): ("21:4", [r"per key $21{:}4$ and $19{:}5$)", _LEADS]),
    (113, "g6k"): ("19:5", [r"per key $21{:}4$ and $19{:}5$)", _LEADS]),
    (101, "fplll"): ("unresolved", [r"unresolved at $n=101$",
                                    r"on both engines, unresolved"]),
    (101, "g6k"): ("unresolved", [r"unresolved at $n=101$",
                                  r"on both engines, unresolved",
                                  r"unresolved on G6K"]),
}

# tab:dimonset (ntru, q=97, beta=20): n -> (printed mean, lo, hi, tex_anchors);
# a row printed as a range or "~0" matches when the 1-dp mean lies in [lo, hi].
DIMONSET_Q = 97
_TIED = [r"59--67 & $\sim 0$", r"tied for $n\!\le\!67$, it spikes at"]
_SPIKE = r"it spikes at $n\!\approx\!71$--$73$"
_PLATEAU = [r"79--89 & $+1.5$--$1.7$", r"settles to a plateau for $n=79$--$89$"]
DIMONSET_PAPER = {
    59: ("~0", 0.0, 0.0, _TIED),
    61: ("~0", 0.0, 0.0, _TIED),
    67: ("~0", 0.0, 0.0, _TIED),
    71: (4.33, None, None, [r"71     & $+4.33$", _SPIKE]),
    73: (9.68, None, None, [r"73     & $+9.68$", _SPIKE]),
    79: ("1.5--1.7", 1.5, 1.7, _PLATEAU),
    83: ("1.5--1.7", 1.5, 1.7, _PLATEAU),
    89: ("1.5--1.7", 1.5, 1.7, _PLATEAU),
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
                       f"p*_mt{DEFAULT_TOURS}", f"n{n:03d}_beta{beta:02d}", "seed*.json")
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


def _key_cells(tree: str, n: int, beta: int):
    """{q: [(seed_id, sd_fires, bkz_fires) per seed file]} over one ladder.
    A seed id fixes the key along the ladder; precisions pool, as in _cell_rate."""
    cells: dict[int, list] = {}
    pat = os.path.join(REPO, "results", "seeds", tree, "q*", f"p*_mt{DEFAULT_TOURS}",
                       f"n{n:03d}_beta{beta:02d}", "seed*.json")
    for f in sorted(glob.glob(pat)):
        with open(f) as fh:
            s = json.load(fh)
        q = int(os.path.relpath(f, REPO).split(os.sep)[3][1:])
        cells.setdefault(q, []).append(
            (s["seed"], _seed_fires(s, "sdbkz", n), _seed_fires(s, "bkz", n)))
    return dict(sorted(cells.items()))


def _per_key(tree: str, n: int, beta: int):
    """(keys SD-BKZ recovers in more cells, keys BKZ does, n_keys)."""
    tot: dict[int, list[int]] = {}
    for rows in _key_cells(tree, n, beta).values():
        for sid, sd, bk in rows:
            t = tot.setdefault(sid, [0, 0])
            t[0] += sd
            t[1] += bk
    return (sum(s > b for s, b in tot.values()),
            sum(s < b for s, b in tot.values()), len(tot))


def _dimonset_advantages(n: int) -> list[float]:
    pat = os.path.join(REPO, "results", "seeds", "ntru", f"q{DIMONSET_Q}",
                       f"p*_mt{DEFAULT_TOURS}", f"n{n:03d}_beta{DSDGAP_BETA:02d}",
                       "seed*.json")
    out = []
    for f in sorted(glob.glob(pat)):
        with open(f) as fh:
            out.append(json.load(fh)["advantage"])
    return out


def _chi2(b: int, c: int) -> float:
    return (b - c) ** 2 / (b + c) if (b + c) else 0.0


def _sign_p_two_sided(b: int, c: int) -> float:
    """Exact two-sided sign-test p (task-specified formula, pure python)."""
    k, m = b + c, min(b, c)
    # Doubling the shared middle term when b == c would exceed 1.
    return min(1.0, 2 * sum(comb(k, i) for i in range(m + 1)) / 2 ** k)


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
               "glob": f"results/seeds/{tree}/q*/p*_mt{DEFAULT_TOURS}/n{n:03d}_beta{BETA:02d}/"}
        for variant, paper, recomputed in (("sdbkz", sd_p, sd_r),
                                           ("bkz", bkz_p, bkz_r)):
            match = recomputed is not None and abs(recomputed - paper) <= 0.1
            records.append({
                "claim_id": f"onset_n{n}_{engine}_{'sd' if variant == 'sdbkz' else 'bkz'}",
                "tex_anchors": tex,
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
            "tex_anchors": tex,
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
               "glob": f"results/seeds/{tree}/q{q}/p*_mt{DEFAULT_TOURS}/n{n:03d}_beta{BETA:02d}/"}

        # 2a. discordant counts b:c (exact string match)
        cnt_match = (b_r == b_p and c_r == c_p)
        records.append({
            "claim_id": f"mcnemar_counts_n{n}_{engine}",
            "tex_anchors": tex,
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
            "tex_anchors": tex,
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
            # Report the value under the convention p_sided names (all
            # two-sided).
            recomputed = two if p_sided == "two-sided" else one
            pmatch = _approx(recomputed, p_p, rtol=5e-2)
            note = (f"Exact binomial sign-test. Paper cites the {p_sided} p. "
                    f"two-sided={two:.3e}, one-sided={one:.3e}.")
            records.append({
                "claim_id": f"signtest_p_n{n}_{engine}",
                "tex_anchors": tex,
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

    # (3) tab:dsdgap onsets + flag gap% -------------------------------------
    for (n, scoring), (sd_p, bkz_p, gap_p, tex) in sorted(DSDGAP_PAPER.items()):
        tree = DSDGAP_TREE[scoring]
        cell = report_cell(tree, n, DSDGAP_BETA, RATE)
        src = {"kind": "seeds",
               "glob": f"results/seeds/{tree}/q*/p*_mt{DEFAULT_TOURS}/"
                       f"n{n:03d}_beta{DSDGAP_BETA:02d}/"}
        for variant, paper in (("sdbkz", sd_p), ("bkz", bkz_p)):
            recomputed = cell[variant]["onset"]
            match = recomputed == paper
            records.append({
                "claim_id": f"dsdgap_{scoring}_n{n}_{'sd' if variant == 'sdbkz' else 'bkz'}",
                "tex_anchors": tex[:1],
                "verbatim": f"tab:dsdgap n={n} {scoring}: SD {sd_p} / BKZ {bkz_p}",
                "paper_value": paper,
                "source": src,
                "method": f"extract_dsd_onset.report_cell(tree='{tree}', n={n}, "
                          f"beta={DSDGAP_BETA}, rate={RATE})['{variant}']['onset']",
                "recomputed_value": recomputed,
                "match": match,
                "status": "RECOMPUTED" if match else "DERIVED-UNRESOLVED",
                "note": f"50%-rate crossing, 1 dp ({cell[variant]['note']}).",
            })
        if gap_p is not None:
            gmatch = cell["gap_pct"] == gap_p
            records.append({
                "claim_id": f"dsdgap_{scoring}_gap_n{n}",
                "tex_anchors": tex,
                "verbatim": f"tab:dsdgap n={n} {scoring}: {gap_p}% SD-vs-BKZ onset gap",
                "paper_value": gap_p,
                "source": src,
                "method": "extract_dsd_onset.report_cell(...)['gap_pct']: "
                          "round(100*(bkz-sd)/sd) on the unrounded onsets",
                "recomputed_value": cell["gap_pct"],
                "match": gmatch,
                "status": "RECOMPUTED" if gmatch else "DERIVED-UNRESOLVED",
                "note": "gap% from the unrounded onsets, as the caption states.",
            })

    # (4) per-key exact-recovery counts, beta=40 ----------------------------
    for (n, engine), (paper, tex) in sorted(PER_KEY_PAPER.items()):
        tree = PER_KEY_TREE[engine]
        up, down, nkeys = _per_key(tree, n, BETA)
        p = _sign_p_two_sided(up, down)
        counts = f"{up}:{down}"
        # "unresolved" = the two-sided sign test does not reach 5%
        match = p >= 0.05 if paper == "unresolved" else counts == paper
        records.append({
            "claim_id": f"per_key_n{n}_{engine}",
            "tex_anchors": tex,
            "verbatim": f"{engine} n={n} beta={BETA} per key (SD-BKZ ahead : BKZ ahead): {paper}",
            "paper_value": paper,
            "source": {"kind": "seeds",
                       "glob": f"results/seeds/{tree}/q*/p*_mt{DEFAULT_TOURS}/"
                               f"n{n:03d}_beta{BETA:02d}/"},
            "method": "per key (seed id), q-cells recovered (_seed_fires) by each "
                      "variant over the ladder; keys with more under SD-BKZ : under BKZ",
            "recomputed_value": counts if paper != "unresolved" else {"counts": counts, "p": p},
            "match": match,
            "status": "RECOMPUTED" if match else "DERIVED-UNRESOLVED",
            "note": f"{nkeys} keys, {nkeys - up - down} ties; "
                    f"exact two-sided sign test p={p:.2g}.",
        })

    # (5) tab:dimonset mean advantage ---------------------------------------
    for n, (paper, lo, hi, tex) in sorted(DIMONSET_PAPER.items()):
        advs = _dimonset_advantages(n)
        mean = sum(advs) / len(advs) if advs else None
        if mean is None:
            match = False
        elif lo is None:
            match = round(mean, 2) == paper
        else:
            match = lo <= round(mean, 1) <= hi
        records.append({
            "claim_id": f"dimonset_mean_n{n}",
            "tex_anchors": tex,
            "verbatim": f"tab:dimonset n={n}: mean advantage {paper}",
            "paper_value": paper,
            "source": {"kind": "seeds",
                       "glob": f"results/seeds/ntru/q{DIMONSET_Q}/p*_mt{DEFAULT_TOURS}/"
                               f"n{n:03d}_beta{DSDGAP_BETA:02d}/"},
            "method": "mean of the per-seed advantage field"
                      + ("" if lo is None else f"; 1-dp mean within [{lo}, {hi}]"),
            "recomputed_value": None if mean is None else round(mean, 3),
            "match": match,
            "status": "RECOMPUTED" if match else "DERIVED-UNRESOLVED",
            "note": f"{len(advs)} seeds.",
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
