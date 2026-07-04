"""Unit tests for the adaptive onset driver's verdict / ratio / wall logic.

The verdict fix (absent recovery key => INCOMPLETE, never a silent NULL) and the
ratio-plateau wall test are the two behaviours that gate a month-long unattended
run, so they are pinned here. All I/O is against a tmp seed tree (REPO monkeypatched);
no real results/ cell is read or written.
"""
import importlib
import json

import pytest

od = importlib.import_module("onset_driver")


def _write_cell(root, n, q, seeds):
    """seeds: list of dicts (already the JSON body). Writes SEEDS-count files."""
    d = (root / f"results/seeds/ntru/q{q}/p{od.P}_mt{od.MT}/n{n}_beta{od.BETA}")
    d.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(seeds):
        (d / f"seed{i:04d}.json").write_text(json.dumps(s))


def _seed(secret_norm2=210, min_bkz=7460, min_sd=7460, recovered=False,
          status="completed", drop_keys=()):
    j = {
        "status": status,
        "secret_norm2": secret_norm2,
        "min_actual_norm2_bkz": min_bkz,
        "min_actual_norm2_sdbkz": min_sd,
        "secret_recovered_bkz": recovered,
        "secret_recovered_sdbkz": recovered,
    }
    for k in drop_keys:
        j.pop(k, None)
    return j


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(od, "REPO", tmp_path)
    return tmp_path


def test_complete_null_cell(repo):
    _write_cell(repo, 173, 3631, [_seed(recovered=False)] * od.SEEDS)
    assert od.verdict(173, 3631) == "NULL"


def test_complete_crack_cell(repo):
    seeds = [_seed(recovered=False)] * (od.SEEDS - 1) + \
            [_seed(min_sd=210, recovered=True)]
    _write_cell(repo, 157, 2203, seeds)
    assert od.verdict(157, 2203) == "CRACK"


def test_incomplete_too_few_seeds(repo):
    _write_cell(repo, 181, 6359, [_seed()] * (od.SEEDS - 1))
    assert od.verdict(181, 6359) is None


def test_missing_recovery_key_is_incomplete_not_null(repo):
    # THE BUG: absent keys must read as INCOMPLETE (re-run), never NULL.
    seeds = [_seed(drop_keys=("secret_recovered_bkz", "secret_recovered_sdbkz"))] \
        * od.SEEDS
    _write_cell(repo, 113, 701, seeds)
    assert od.verdict(113, 701) is None


def test_uncompleted_status_is_incomplete(repo):
    seeds = [_seed()] * (od.SEEDS - 1) + [_seed(status="running")]
    _write_cell(repo, 167, 2657, seeds)
    assert od.verdict(167, 2657) is None


def test_cell_ratio_picks_min_over_engines_and_seeds(repo):
    seeds = [_seed(min_bkz=7460, min_sd=10000)] * (od.SEEDS - 1) + \
            [_seed(min_bkz=420, min_sd=10000)]     # 420/210 = 2.0 is the best
    _write_cell(repo, 167, 2657, seeds)
    assert od.cell_ratio(167, 2657) == pytest.approx(2.0)


def test_wall_reached_on_low_saturated_band(repo):
    # 173: q3631 ratio ~43x, q4073 ratio ~52x (got WORSE, both in 10..500) => wall.
    _write_cell(repo, 173, 3631, [_seed(min_bkz=9030, min_sd=9030)] * od.SEEDS)
    _write_cell(repo, 173, 4073, [_seed(min_bkz=10920, min_sd=10920)] * od.SEEDS)
    assert od._wall_reached(173, [3631, 4073]) is True


def test_wall_not_reached_when_ratio_falling(repo):
    # cliff approaching: ratio 40x -> 5x (fell past IMPROVE) => keep hunting.
    _write_cell(repo, 149, 2000, [_seed(min_bkz=8400, min_sd=8400)] * od.SEEDS)
    _write_cell(repo, 149, 2400, [_seed(min_bkz=1050, min_sd=1050)] * od.SEEDS)
    assert od._wall_reached(149, [2000, 2400]) is False


def test_wall_not_reached_in_rising_thousands(repo):
    # THE MUST-FIX #1 REGRESSION: pre-cliff ratios rise through the THOUSANDS
    # (n=181-low: 37868 -> 46245). Old logic (>WALL_RATIO lower-bound only) called
    # this a "plateau" and walled one step below a real crack. New band gate
    # (r_last < WALL_HI=500) must reject it so hunting continues.
    _write_cell(repo, 163, 2000, [_seed(secret_norm2=1, min_bkz=37868,
                                        min_sd=37868)] * od.SEEDS)
    _write_cell(repo, 163, 2400, [_seed(secret_norm2=1, min_bkz=46245,
                                        min_sd=46245)] * od.SEEDS)
    assert od._wall_reached(163, [2000, 2400]) is False


def test_wall_needs_two_cells(repo):
    _write_cell(repo, 173, 4073, [_seed(min_bkz=10920, min_sd=10920)] * od.SEEDS)
    assert od._wall_reached(173, [4073]) is False


def test_known_skips_incomplete_cells(repo):
    _write_cell(repo, 167, 2657, [_seed(recovered=False)] * od.SEEDS)      # NULL
    _write_cell(repo, 167, 3061, [_seed()] * (od.SEEDS - 2))               # partial
    k = od.known(167)
    assert k == {2657: "NULL"}


# ---------------------------------------------------------------------------
# Audit 2026-07-04 #3 hardening: densification, variant rates, lock pid-reuse.
# ---------------------------------------------------------------------------

def _seed_rates(bkz, sd):
    j = _seed()
    j["secret_recovered_bkz"] = bkz
    j["secret_recovered_sdbkz"] = sd
    return j


def test_variant_rates(repo):
    seeds = [_seed_rates(True, True)] * 5 + [_seed_rates(False, True)] * 5 \
        + [_seed_rates(False, False)] * (od.SEEDS - 10)
    _write_cell(repo, 157, 2411, seeds)
    assert od._variant_rates(157, 2411) == pytest.approx((0.25, 0.5))


def test_variant_rates_incomplete_is_none(repo):
    _write_cell(repo, 157, 2411, [_seed_rates(True, True)] * (od.SEEDS - 1))
    assert od._variant_rates(157, 2411) is None


def test_densify_stops_when_both_variants_cross(repo, monkeypatch):
    # highest crack cell already at bkz 55% / sd 60% -> no extra cells run.
    seeds = [_seed_rates(True, True)] * 11 + \
            [_seed_rates(False, True)] * 1 + \
            [_seed_rates(False, False)] * (od.SEEDS - 12)
    _write_cell(repo, 157, 2411, seeds)
    ran = []
    monkeypatch.setattr(od, "run_cell", lambda n, q, d, dry: ran.append(q) or True)
    od._densify(157, deadline=float("inf"), dry=False)
    assert ran == []


def test_densify_steps_up_until_target(repo, monkeypatch):
    # crack cell at 5%/10% -> densify probes upward; fake each new cell landing
    # at 60%/60% so exactly one extra cell is needed.
    seeds = [_seed_rates(False, True)] * 2 + \
            [_seed_rates(True, False)] * 1 + \
            [_seed_rates(False, False)] * (od.SEEDS - 3)
    _write_cell(repo, 157, 2203, seeds)
    ran = []

    def fake_run_cell(n, q, deadline, dry):
        ran.append(q)
        _write_cell(repo, n, q, [_seed_rates(True, True)] * 12
                    + [_seed_rates(False, False)] * (od.SEEDS - 12))
        return True

    monkeypatch.setattr(od, "run_cell", fake_run_cell)
    od._densify(157, deadline=float("inf"), dry=False)
    assert len(ran) == 1
    assert ran[0] > 2203                    # probed ABOVE the first-crack
    assert od.isprime(ran[0])


def test_densify_no_cracks_is_noop(repo, monkeypatch):
    _write_cell(repo, 173, 3631, [_seed_rates(False, False)] * od.SEEDS)
    ran = []
    monkeypatch.setattr(od, "run_cell", lambda n, q, d, dry: ran.append(q) or True)
    od._densify(173, deadline=float("inf"), dry=False)
    assert ran == []


def test_lock_reclaims_reused_pid(repo, monkeypatch, tmp_path):
    # A live pid whose cmdline is NOT onset_driver = pid reuse -> reclaim.
    lock = tmp_path / "onset_driver.lock"
    monkeypatch.setattr(od, "LOCK", lock)
    lock.write_text("1")                    # pid 1 = init, alive, not our driver
    assert od._acquire_lock() is True
    assert lock.read_text() == str(__import__("os").getpid())


def test_lock_blocks_on_live_onset_driver(repo, monkeypatch, tmp_path):
    import os
    lock = tmp_path / "onset_driver.lock"
    monkeypatch.setattr(od, "LOCK", lock)
    lock.write_text(str(os.getpid()))       # this pytest process is "alive"
    monkeypatch.setattr(
        od.Path, "read_bytes",
        lambda self: b"python3\0scripts/onset_driver.py\0",
    )
    assert od._acquire_lock() is False
