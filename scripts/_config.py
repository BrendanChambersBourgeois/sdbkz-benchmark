"""Campaign config loader for the SD-BKZ benchmark.

Parses ``config/sweep.toml`` into a :class:`Campaign` dataclass with
strict validation. Unknown keys are rejected so a typo in the TOML
cannot silently produce a wrong-precision or wrong-q sweep. Inheritance
between campaigns is resolved here; cycles are rejected with an
explicit error.

This module is the data-side counterpart of the v1.2 ``_math_core`` /
``_bkz_core`` consolidation: those modules consolidated the *logic*
duplicated across sweep wrappers; this module consolidates the
*constants*. No runner currently imports from here — the existing
hardcoded constants at the top of each ``scripts/run_*.py`` continue
to be the production source of truth. The TOML serves three purposes
until the next migration window:

  - Single-file audit surface for reviewers asking "what parameters
    does each campaign use?"
  - Round-trip schema validation in CI catches typos / version drift
    before any future migration that consumes the file.
  - Foundation for the v2 per-seed-JSON ``campaign`` provenance field
    (out of scope here; would break SHA-256 reproducibility chain).

No side effects on import. All paths absolute. No environment reads.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import tomllib
from typing import Any

from generators import available_generators

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "sweep.toml")

# Schema-supported field names per campaign block, after inheritance is
# applied. Anything else in a campaign block raises ConfigError.
CAMPAIGN_FIELDS: frozenset[str] = frozenset({
    "description",
    "inherits",
    "q",
    "precision",
    "beta_grid",
    "n_grid",
    "tours_by_beta",
    "num_seeds",
    "store_per_tour",
    "generator",
    "seed_tag",
    "backend",
    "metric_float_type",
})

# Top-level (non-campaign) keys allowed in the TOML root. `default` is
# treated as a campaign base for unspecified fields. `config_version`
# pins the schema generation.
ROOT_KEYS: frozenset[str] = frozenset({"config_version", "default", "campaigns"})

# Maximum inheritance chain depth. A campaign tree deeper than this
# almost certainly indicates a cycle even if the explicit cycle check
# missed it; preserved as a defensive ceiling.
MAX_INHERIT_DEPTH: int = 8


class ConfigError(ValueError):
    """Raised on any schema, type, or inheritance violation."""


@dataclasses.dataclass(frozen=True)
class Campaign:
    """Resolved configuration for one named sweep campaign.

    All fields are set after inheritance resolution and default merge,
    so a caller sees one flat structure regardless of how the TOML
    organised the source declaration.
    """
    name: str
    description: str
    q: int
    precision: int
    beta_grid: tuple[int, ...]
    n_grid: tuple[int, ...]
    tours_by_beta: dict[int, int]
    num_seeds: int
    store_per_tour: bool
    # Name of the lattice generator (see generators.GENERATORS). Defaulted
    # so every pre-existing campaign resolves to the historical LWE-Kannan
    # construction — byte-for-byte unchanged.
    generator: str = "lwe_kannan"
    # Output-tree tag under results/seeds/. None → the dispatcher's default
    # for the generator (e.g. "ntru"). A campaign sets this to route its
    # seeds to a SEPARATE tree without touching the canonical one — e.g.
    # "ntru_patched" for a Kahan-patched-fplll rerun (paper §8 validation).
    # Must be one of _seed_paths._KNOWN_CAMPAIGNS.
    seed_tag: str | None = None
    # Reduction engine: "fplll" (default, all historical campaigns) or "g6k".
    # Threaded through to _bkz_core.run_single(backend=…). A g6k campaign MUST
    # run inside the g6k image (sdbkz-g6k:ref); the fplll image has no g6k.
    backend: str = "fplll"
    # Float type for the MEASUREMENT GSO only (the reduction is always mpfr).
    # "double" (default) = the historical byte-identical path; "mpfr" removes
    # the catastrophic get_r cancellation at frontier dims (n>=157) that
    # clamps gs_lognorms to the -345 sentinel (deep audit 2026-07-04 finding
    # 1). fplll-only: a g6k campaign must leave this at "double".
    metric_float_type: str = "double"


def _read_toml(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        raise ConfigError(f"campaign config not found: {path}")
    with open(path, "rb") as f:
        try:
            return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: TOML parse error: {e}") from e


def _normalise_tours_by_beta(raw: Any, ctx: str) -> dict[int, int]:
    """Coerce a tours_by_beta sub-table to a ``dict[int, int]``.

    TOML inline tables require string keys; the schema uses
    ``{"20" = 50, "30" = 70, ...}`` so we cast back to int.
    """
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{ctx}: tours_by_beta must be a table mapping β → tours, "
            f"got {type(raw).__name__}"
        )
    out: dict[int, int] = {}
    for k, v in raw.items():
        try:
            beta_int = int(k)
            tours_int = int(v)
        except (ValueError, TypeError) as e:
            raise ConfigError(
                f"{ctx}: tours_by_beta key/value must be int-castable; "
                f"got key={k!r} val={v!r}"
            ) from e
        if tours_int <= 0:
            raise ConfigError(
                f"{ctx}: tours_by_beta[{beta_int}] must be positive, "
                f"got {tours_int}"
            )
        out[beta_int] = tours_int
    return out


def _resolve_inheritance(
    name: str,
    blocks: dict[str, dict[str, Any]],
    default: dict[str, Any],
    seen: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Merge a campaign block with its inheritance chain and the default.

    Resolution order (later overrides earlier):
      1. top-level [default] table
      2. every ancestor through `inherits`, root-most first
      3. the requested block itself
    """
    if name in seen:
        cycle = " → ".join(seen + (name,))
        raise ConfigError(f"campaign inheritance cycle: {cycle}")
    if len(seen) >= MAX_INHERIT_DEPTH:
        chain = " → ".join(seen + (name,))
        raise ConfigError(
            f"campaign inheritance depth exceeded {MAX_INHERIT_DEPTH}: {chain}"
        )
    if name not in blocks:
        raise ConfigError(
            f"unknown campaign '{name}'; available: "
            f"{sorted(blocks.keys())!r}"
        )
    block = blocks[name]
    parent_name = block.get("inherits")
    if parent_name is not None:
        merged = _resolve_inheritance(
            parent_name, blocks, default, seen + (name,)
        )
    else:
        merged = dict(default)
    for k, v in block.items():
        if k == "inherits":
            continue
        merged[k] = v
    return merged


def _to_campaign(name: str, merged: dict[str, Any]) -> Campaign:
    """Type-check, coerce, and freeze a resolved block into a Campaign."""
    unknown = set(merged) - CAMPAIGN_FIELDS
    if unknown:
        raise ConfigError(
            f"campaigns.{name}: unknown keys {sorted(unknown)!r}; "
            f"allowed: {sorted(CAMPAIGN_FIELDS)!r}"
        )
    required = {"q", "precision", "beta_grid", "n_grid",
                "tours_by_beta", "num_seeds"}
    missing = required - set(merged)
    if missing:
        raise ConfigError(
            f"campaigns.{name}: missing required keys {sorted(missing)!r}"
        )

    ctx = f"campaigns.{name}"
    beta_grid = tuple(int(b) for b in merged["beta_grid"])
    n_grid = tuple(int(n) for n in merged["n_grid"])
    tours_by_beta = _normalise_tours_by_beta(merged["tours_by_beta"], ctx)

    for b in beta_grid:
        if b not in tours_by_beta:
            raise ConfigError(
                f"{ctx}: β={b} appears in beta_grid but has no entry in "
                f"tours_by_beta (keys: {sorted(tours_by_beta)!r})"
            )

    if int(merged["q"]) <= 0:
        raise ConfigError(f"{ctx}: q must be positive, got {merged['q']!r}")
    if int(merged["precision"]) <= 0:
        raise ConfigError(
            f"{ctx}: precision must be positive, got {merged['precision']!r}"
        )
    if int(merged["num_seeds"]) <= 0:
        raise ConfigError(
            f"{ctx}: num_seeds must be positive, got {merged['num_seeds']!r}"
        )
    if not n_grid:
        raise ConfigError(f"{ctx}: n_grid must be non-empty")
    if not beta_grid:
        raise ConfigError(f"{ctx}: beta_grid must be non-empty")
    for n in n_grid:
        if n <= 0:
            raise ConfigError(f"{ctx}: n_grid entries must be positive; got {n}")
    for b in beta_grid:
        if b <= 0:
            raise ConfigError(f"{ctx}: beta_grid entries must be positive; got {b}")

    generator = str(merged.get("generator", "lwe_kannan"))
    if generator not in available_generators():
        raise ConfigError(
            f"{ctx}: unknown generator {generator!r}; "
            f"available: {sorted(available_generators())!r}"
        )

    backend = str(merged.get("backend", "fplll"))
    if backend not in ("fplll", "g6k"):
        raise ConfigError(
            f"{ctx}: unknown backend {backend!r}; expected 'fplll' or 'g6k'"
        )

    metric_float_type = str(merged.get("metric_float_type", "double"))
    if metric_float_type not in ("double", "mpfr"):
        raise ConfigError(
            f"{ctx}: unknown metric_float_type {metric_float_type!r}; "
            "expected 'double' or 'mpfr'"
        )
    if backend == "g6k" and metric_float_type != "double":
        raise ConfigError(
            f"{ctx}: metric_float_type={metric_float_type!r} is fplll-only; "
            "the g6k backend measures through the Siever's GSO"
        )

    # seed_tag must name a known output tree (else a typo only surfaces at
    # worker runtime inside seed_dir_for). Validate here to fail fast.
    seed_tag_val = merged.get("seed_tag")
    if seed_tag_val:
        from _seed_paths import _KNOWN_CAMPAIGNS
        if str(seed_tag_val) not in _KNOWN_CAMPAIGNS:
            raise ConfigError(
                f"{ctx}: unknown seed_tag {seed_tag_val!r}; must be one of "
                f"{sorted(_KNOWN_CAMPAIGNS)}"
            )

    return Campaign(
        name=name,
        description=str(merged.get("description", "")),
        q=int(merged["q"]),
        precision=int(merged["precision"]),
        beta_grid=beta_grid,
        n_grid=n_grid,
        tours_by_beta=tours_by_beta,
        num_seeds=int(merged["num_seeds"]),
        store_per_tour=bool(merged.get("store_per_tour", False)),
        generator=generator,
        seed_tag=(str(merged["seed_tag"]) if merged.get("seed_tag")
                  else None),
        backend=backend,
        metric_float_type=metric_float_type,
    )


def load_campaign(name: str, *, path: str | None = None) -> Campaign:
    """Load and validate one named campaign from ``config/sweep.toml``.

    Raises :class:`ConfigError` on any schema violation, unknown key,
    inheritance cycle, missing required field, or unknown campaign name.
    """
    all_c = load_all_campaigns(path=path)
    if name not in all_c:
        raise ConfigError(
            f"unknown campaign '{name}'; available: {sorted(all_c.keys())!r}"
        )
    return all_c[name]


def load_all_campaigns(*, path: str | None = None) -> dict[str, Campaign]:
    """Load and validate every campaign in the config file.

    Returns ``{campaign_name: Campaign}`` with inheritance resolved
    and defaults merged. Raises :class:`ConfigError` on any violation
    in any campaign — failure is all-or-nothing so a CI gate catches
    typos in a single line, not just the one the CI happened to read.
    """
    resolved_path = path or DEFAULT_CONFIG_PATH
    payload = _read_toml(resolved_path)

    unknown_root = set(payload) - ROOT_KEYS
    if unknown_root:
        raise ConfigError(
            f"{resolved_path}: unknown root keys {sorted(unknown_root)!r}; "
            f"allowed: {sorted(ROOT_KEYS)!r}"
        )

    version = payload.get("config_version")
    if version != 1:
        raise ConfigError(
            f"{resolved_path}: unsupported config_version {version!r}; "
            "this loader expects version 1"
        )

    default_block = payload.get("default", {}) or {}
    if not isinstance(default_block, dict):
        raise ConfigError(
            f"{resolved_path}: [default] must be a table, "
            f"got {type(default_block).__name__}"
        )

    campaigns = payload.get("campaigns", {}) or {}
    if not isinstance(campaigns, dict):
        raise ConfigError(
            f"{resolved_path}: [campaigns] must be a table-of-tables, "
            f"got {type(campaigns).__name__}"
        )

    out: dict[str, Campaign] = {}
    for name, block in campaigns.items():
        if not isinstance(block, dict):
            raise ConfigError(
                f"campaigns.{name} must be a table, got {type(block).__name__}"
            )
        merged = _resolve_inheritance(name, campaigns, default_block)
        out[name] = _to_campaign(name, merged)
    return out


def _main(argv: list[str] | None = None) -> int:
    """CLI for `python3 -m _config <campaign>` ad-hoc inspection.

    Pretty-prints the resolved Campaign or lists all campaign names.
    Returns 0 on success, non-zero on ConfigError.
    """
    argv = list(sys.argv[1:]) if argv is None else argv
    try:
        if not argv or argv[0] in ("-h", "--help"):
            print("usage: python3 -m _config <campaign> | --list")
            return 0
        if argv[0] == "--list":
            for name in sorted(load_all_campaigns().keys()):
                print(name)
            return 0
        campaign = load_campaign(argv[0])
        for field in dataclasses.fields(campaign):
            print(f"{field.name}: {getattr(campaign, field.name)}")
        return 0
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(_main())
