# scripts/archive/

One-shot verification + migration scripts retained for audit-chain
reproducibility. They are NOT called during normal operation; the
v1.2 consolidation phases they verified are long-since merged, and
the v1.3 layout migration they performed has completed.

Kept on-disk (rather than deleted) because each documents a
specific bit-identity gate or migration step that future-reader
or future-self may need to re-run to convince themselves the
historical claim still holds.

## Inventory

- **`confirm_v1_2.py`** — End-to-end 30-seed confirmation across
  four `run_single` paths against the v1.1.0 baseline JSONs. Gated
  the v1.2 consolidation merge (see ADR-001).
- **`confirm_extra_compare.py`** — Extra-group bit-identity check
  for the out-of-band parallel groups (cliff 500-bit, q3329 n=90,
  cliff n=110/130). Companion to `confirm_v1_2.py`.
- **`split_fat_seeds.py`** — Splits "fat" (per-tour-array)
  q=3329 seed JSONs into a manifest + a side-file payload. Used
  during the v1.3 layout migration to reduce manifest-entry size;
  paper-cited seeds retain the canonical "fat" form.
- **`rerun_n127_patched.py`** — Kahan-patch validation #2: reruns the
  contaminated n=127 NTRU seeds (q∈{971,1087,1201}, β=20, p=1000)
  under PATCHED fplll to show the paper §8 catastrophic-cancellation
  floor clamp (b1 = −345.388) vanish. Generated the `ntru_patched/`
  corpus; the recovery (−345 → ~−0.1) is the §8 validation-#2 claim.
  Run inside the patched image (`sdbkz-fplll-patched`), writes to a
  separate `results/seeds/ntru_patched/` tree (locked seeds untouched).
- **`test_log_clamp_wrappers.py`** — Standalone parity check that
  the seven `_log_clamp` / `_log_clamp_cloud` wrappers emit
  identical JSONL schema. Gated the v1.2 Phase 4a swap.
- **`test_math_core_parity.py`** — 576-comparison standalone
  parity check across `ln_fixed_point` / `build_lwe_kannan`
  between `_math_core` and the (now-retired) per-script copies.
  Gated v1.2 Phases 1–3. See ADR-001.

## Why these are not under tests/

Each is a standalone `__main__` runner with `def main()` and
`if __name__ == "__main__"`. They do not define pytest-style
`test_*` functions, so `pytest tests/` would not collect them
automatically. Invoke directly:

```bash
python3 scripts/archive/confirm_v1_2.py
python3 scripts/archive/test_math_core_parity.py
```

## Re-running

All scripts import their dependencies from `scripts/` via an
explicit `sys.path` insert that resolves to the project root.
No PYTHONPATH setup required; just run from the repo root.
