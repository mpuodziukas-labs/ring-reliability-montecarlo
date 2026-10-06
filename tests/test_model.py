import math, random
from ringmc import model, params

ROWS = params.load(params.default_path())
CURRENT = params.resolve(ROWS, "current")


def ranges(**kw):
    """zero ranges with overrides like wedge__rate_per_h=(a, b)"""
    r = model.zero_ranges()
    for k, v in kw.items():
        r[k.replace("__", ".")] = (v[0], v[1], "ESTIMATED")
    return r


def test_seed_determinism():
    a = model.simulate(CURRENT, 500, seed=7)
    b = model.simulate(CURRENT, 500, seed=7)
    c = model.simulate(CURRENT, 500, seed=8)
    assert a == b
    assert a != c


def test_zero_failure_rate_gives_probability_exactly_one():
    s = model.summarize(model.simulate(model.zero_ranges(), 2000, seed=1))
    assert s["p_full"] == 1.0 and s["p_clean"] == 1.0
    assert s["mean_down"] == 0.0 and s["p95_down"] == 0.0


def test_always_down_owner_only_class_gives_zero():
    r = ranges(wedge__rate_per_h=(600, 600), wedge__p_owner=(1, 1))
    s = model.summarize(model.simulate(r, 40, seed=1))
    assert s["p_full"] == 0.0
    assert s["mean_down"] > 299.0


def test_poisson_analytic_instant_heal_matches_exp_minus_rate_t():
    rate = 0.3                                            # per hour, T = 5 h
    r = ranges(poison__rate_per_h=(rate, rate))
    n = 20000
    s = model.summarize(model.simulate(r, n, seed=11))
    want = math.exp(-rate * 5)
    lo, hi = s["p_clean_ci"]
    assert lo <= want <= hi, (want, lo, hi)
    assert s["p_full"] == 1.0                             # instant heal never costs a minute


def test_poisson_mean_event_count_scales_with_rate():
    a = model.simulate(ranges(poison__rate_per_h=(0.5, 0.5)), 4000, seed=3)
    b = model.simulate(ranges(poison__rate_per_h=(1.0, 1.0)), 4000, seed=3)
    ma = sum(x[1] for x in a) / len(a)
    mb = sum(x[1] for x in b) / len(b)
    assert abs(ma - 2.5) < 0.15 and abs(mb - 5.0) < 0.2


def test_heal_time_is_applied_detect_plus_heal():
    v = {"poison.detect_min": 2.0, "poison.heal_min": 3.0, "poison.p_owner": 0.0}
    rng = random.Random(5)
    ds = [model.outage_end(rng, v, "poison", 10.0) - 10.0 for _ in range(20000)]
    assert abs(sum(ds) / len(ds) - 5.0) < 0.15


def test_owner_probability_means_down_to_end_of_night():
    v = {"poison.detect_min": 0.0, "poison.heal_min": 0.0, "poison.p_owner": 1.0}
    assert model.outage_end(random.Random(1), v, "poison", 10.0) == model.NIGHT_MIN


def test_heal_time_drives_downtime_in_a_whole_run():
    r = ranges(poison__rate_per_h=(600, 600), poison__heal_min=(10, 10))
    s = model.summarize(model.simulate(r, 40, seed=2))
    assert 299.0 < s["mean_down"] <= 300.0                 # overlapping outages merge, never exceed the night


def test_election_drop_probability_gates_half_placement():
    base = dict(election__rate_per_h=(600, 600), half_placement__heal_min=(10, 10))
    none = model.summarize(model.simulate(ranges(election__p_drop=(0, 0), **base), 40, seed=2))
    allp = model.summarize(model.simulate(ranges(election__p_drop=(1, 1), **base), 40, seed=2))
    assert none["p_full"] == 1.0 and none["mean_down"] == 0.0
    assert allp["p_full"] == 0.0


def test_wilson_known_values():
    lo, hi = model.wilson(50, 100)
    assert abs(lo - 0.4038) < 1e-3 and abs(hi - 0.5962) < 1e-3
    lo0, hi0 = model.wilson(0, 100)
    assert lo0 == 0.0 and 0.03 < hi0 < 0.04
    lo1, hi1 = model.wilson(100, 100)
    assert hi1 == 1.0


def test_p95_nearest_rank():
    assert model.percentile95(list(range(1, 101))) == 95
    assert model.percentile95([0.0] * 10) == 0.0


def test_each_single_fix_does_not_lower_p_full_and_all_three_help():
    n = 3000
    base = model.summarize(model.simulate(CURRENT, n, seed=4))["p_full"]
    allfix = model.summarize(model.simulate(
        params.resolve(ROWS, "current", ["fix_poison", "fix_halfplace", "fix_wedge"]), n, seed=4))["p_full"]
    assert allfix > base
    for fx in ("fix_poison", "fix_halfplace", "fix_wedge"):
        p = model.summarize(model.simulate(params.resolve(ROWS, "current", [fx]), n, seed=4))["p_full"]
        assert p >= base - 0.01, fx


def test_before_is_worse_than_current():
    n = 3000
    b = model.summarize(model.simulate(params.resolve(ROWS, "before"), n, seed=4))["p_full"]
    c = model.summarize(model.simulate(CURRENT, n, seed=4))["p_full"]
    assert b < c


def test_tornado_ranks_the_parameter_that_moves_the_answer():
    r = ranges(wedge__rate_per_h=(0.0, 0.5), wedge__p_owner=(1, 1))
    r["poison.rate_per_h"] = (0.0, 0.01, "ESTIMATED")
    rows = model.tornado(r, 3000, seed=9)
    assert rows[0]["key"] == "wedge.rate_per_h"
    assert rows[0]["swing"] > rows[1]["swing"] >= 0
    assert all(x["key"] != "wedge.p_owner" for x in rows)  # fixed value, no range, not a tornado bar


def test_recovery_owner_only_class_never_recovers_instant_heal_always_does():
    own = model.recovery_totals(ranges(wedge__rate_per_h=(600, 600), wedge__p_owner=(1, 1)), 20, seed=1)
    assert own["c6_worker_gpu_wedge"][0] > 0 and own["c6_worker_gpu_wedge"][1] == 0
    ok = model.recovery_totals(ranges(poison__rate_per_h=(5, 5)), 200, seed=1)
    assert ok["c1_master_death_on_malformed_gossip"][0] > 0
    assert ok["c1_master_death_on_malformed_gossip"][1] == ok["c1_master_death_on_malformed_gossip"][0]


def test_recovery_heal_past_the_night_is_not_a_recovery():
    r = model.recovery_totals(ranges(probe_collision__rate_per_h=(60, 60), probe_collision__heal_min=(1e6, 1e6)), 20, seed=2)
    assert r["c2_probe_collision"][0] > 0 and r["c2_probe_collision"][1] == 0


def test_recovery_election_without_a_dropped_runner_recovers_and_a_stuck_one_does_not():
    base = dict(election__rate_per_h=(60, 60))
    a = model.recovery_totals(ranges(election__p_drop=(0, 0), **base), 20, seed=3)["c3_heavy_job_reelection"]
    b = model.recovery_totals(ranges(election__p_drop=(1, 1), half_placement__p_owner=(1, 1), **base), 20, seed=3)["c3_heavy_job_reelection"]
    assert a[0] > 0 and a[1] == a[0] and b[0] > 0 and b[1] == 0


def test_recovery_covers_six_classes_and_every_one_is_injected_with_current_params():
    r = model.recovery_totals(CURRENT, 800, seed=5)
    assert len(r) == 6
    assert all(inj > 0 and 0 <= rec <= inj for inj, rec in r.values())
    assert r == model.recovery_totals(CURRENT, 800, seed=5)
