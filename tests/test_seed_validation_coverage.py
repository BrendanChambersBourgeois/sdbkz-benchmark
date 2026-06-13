"""INC-45 Phase 2 — structural guard for seed-validation coverage.

Root cause of INC-45: the CI `validate_seeds.py` directory list in
`.github/workflows/build-and-verify.yml` was hand-maintained and silently
drifted. The entire NTRU family (`ntru/`, `ntru_g6k/`, `ntru_patched/` —
7,476 seeds, the whole empirical basis of Paper 2) was never validated
because nobody added it to that list, and nothing complained.

This guard fails the build the moment a seed family under
`results/seeds/` is neither fed to `validate_seeds.py` in CI nor placed on
an explicit, documented deferral allowlist. The allowlist must shrink to
empty as INC-45 remediation completes (Phase 3 wires `ntru_g6k`; Phase 4
wires `ntru` + `ntru_patched` after the volume-drift classification).

The pure helpers (`validated_families`, `coverage_violations`) are unit-
tested against synthetic inputs; the repo-level tests run them against the
actual workflow file and on-disk tree, so this rides the existing
`pytest tests/` CI gate with no extra wiring.
"""
import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "build-and-verify.yml")
SEEDS_ROOT = os.path.join(REPO, "results", "seeds")

# Families deliberately NOT yet in the CI validate_seeds list, each with a
# reason. This set MUST shrink to empty as remediation lands. Wiring a
# family into CI without removing it here is caught by
# `test_deferred_allowlist_is_honest`; dropping a family from disk-coverage
# without either validating or deferring it is caught by
# `test_no_unguarded_seed_family`.
DEFERRED_FAMILIES: dict[str, str] = {}
# EMPTY — INC-45 fully remediated (2026-06-14). The allowlist has shrunk to
# empty as required: every results/seeds/* family is now CI-validated.
#   - ntru_g6k removed Phase 3 (validates 1784/1784 clean).
#   - ntru + ntru_patched removed Phase 4b: volume-drift classified (verdict
#     numerical/Kahan-family for the 0.1-10 band, structural crack for >10),
#     both wired into the CI validate_seeds list and handled via _incident
#     (id=45 numerical, id=46 crack) — 0 errors, drift never silenced.


def validated_families(workflow_text: str) -> set[str]:
    """Return the set of `results/seeds/<family>/` dirs passed to
    `validate_seeds.py` in the given workflow text.

    Only tokens that appear within a `validate_seeds.py` invocation (from
    the command up to the next `- name:` step boundary) are counted, so
    `results/seeds/...` references in unrelated steps (e.g. verify.sh) do
    not leak in.
    """
    fams: set[str] = set()
    for m in re.finditer(r"validate_seeds\.py(.*?)(?=\n\s+- name:|\Z)",
                          workflow_text, re.S):
        fams.update(re.findall(r"results/seeds/([A-Za-z0-9_]+)/", m.group(1)))
    return fams


def coverage_violations(disk: set[str], validated: set[str],
                        deferred: set[str]) -> list[str]:
    """Families present on disk that are neither validated nor deferred.

    Returns a sorted list of the offending family names (empty == OK).
    """
    return sorted(disk - validated - deferred)


def _disk_families() -> set[str]:
    return {d for d in os.listdir(SEEDS_ROOT)
            if os.path.isdir(os.path.join(SEEDS_ROOT, d))}


# --------------------------------------------------------------------------
# Pure-logic unit tests (synthetic inputs)
# --------------------------------------------------------------------------
def test_parser_extracts_dirs_from_invocation():
    txt = (
        "      - name: Validate\n"
        "        run: |\n"
        "          python3 scripts/validate_seeds.py --strict \\\n"
        "            results/seeds/main/ results/seeds/q3329/\n"
        "      - name: Next step\n"
        "        run: results/seeds/should_not_count/\n"
    )
    assert validated_families(txt) == {"main", "q3329"}


def test_parser_spans_multiple_invocations_in_one_step():
    txt = (
        "      - name: Validate\n"
        "        run: |\n"
        "          python3 scripts/validate_seeds.py results/seeds/main/\n"
        "          python3 scripts/validate_seeds.py results/seeds/tours3x/\n"
        "      - name: After\n"
    )
    assert validated_families(txt) == {"main", "tours3x"}


def test_parser_ignores_seeds_refs_outside_validate_step():
    txt = (
        "      - name: Other\n"
        "        run: cp results/seeds/sneaky/x .\n"
        "      - name: Validate\n"
        "        run: python3 scripts/validate_seeds.py results/seeds/main/\n"
    )
    assert validated_families(txt) == {"main"}


def test_coverage_clean_when_all_validated():
    assert coverage_violations({"main", "q3329"}, {"main", "q3329"}, set()) == []


def test_coverage_clean_when_deferred():
    assert coverage_violations({"main", "ntru"}, {"main"}, {"ntru"}) == []


def test_coverage_flags_unguarded_family():
    assert coverage_violations({"main", "leak"}, {"main"}, set()) == ["leak"]


def test_coverage_flags_sorted_and_multiple():
    assert coverage_violations(
        {"zfam", "afam", "main"}, {"main"}, set()) == ["afam", "zfam"]


# --------------------------------------------------------------------------
# Repo-level guards (real workflow + on-disk tree)
# --------------------------------------------------------------------------
def test_no_unguarded_seed_family():
    """Every family under results/seeds/ is validated in CI or explicitly
    deferred. This is the INC-45 regression guard."""
    validated = validated_families(open(WORKFLOW).read())
    disk = _disk_families()
    violations = coverage_violations(disk, validated, set(DEFERRED_FAMILIES))
    assert not violations, (
        f"seed families neither validated in CI nor on the deferral "
        f"allowlist: {violations}. Add them to the validate_seeds dir list "
        f"in {os.path.relpath(WORKFLOW, REPO)}, or add to DEFERRED_FAMILIES "
        f"with a documented reason (see INC-45)."
    )


def test_deferred_allowlist_is_honest():
    """Deferred families must (a) actually exist on disk and (b) not already
    be validated in CI — otherwise the allowlist entry is stale and should
    be removed (the whole point is for this set to shrink to empty)."""
    validated = validated_families(open(WORKFLOW).read())
    disk = _disk_families()
    stale_validated = sorted(set(DEFERRED_FAMILIES) & validated)
    assert not stale_validated, (
        f"families are deferred AND already in CI validate_seeds — remove "
        f"from DEFERRED_FAMILIES: {stale_validated}"
    )
    missing = sorted(set(DEFERRED_FAMILIES) - disk)
    assert not missing, (
        f"DEFERRED_FAMILIES names a family not on disk: {missing}"
    )


@pytest.mark.parametrize("fam", ["main", "q3329", "cliff500",
                                 "convergence", "fplll_sensitivity", "tours3x"])
def test_known_lwe_families_are_validated(fam):
    """The pre-INC-45 validated families must stay wired in — a regression
    here means someone dropped a family from the CI list."""
    assert fam in validated_families(open(WORKFLOW).read())
