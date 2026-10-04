"""Mutation check: break one piece of the model in a scratch copy, the named tests must go RED.
A control run of the same tests on an untouched copy must pass first."""
import pathlib, shutil, subprocess, sys, tempfile
ROOT = pathlib.Path(__file__).parent
M, P = "ringmc/model.py", "ringmc/params.py"
TM, TP = "tests/test_model.py", "tests/test_params.py"
# (name, file, text to remove, text to put in, tests that must fail)
MUTANTS = [
    ("poisson: rate not converted to per minute", M, "rate_per_h / 60.0", "rate_per_h", [TM + "::test_poisson_analytic_instant_heal_matches_exp_minus_rate_t"]),
    ("poisson: arrivals run past the night", M, "        if t >= horizon:", "        if t >= horizon * 2:", [TM + "::test_poisson_mean_event_count_scales_with_rate"]),
    ("heal: heal time never applied", M, "t + d + h", "t + d", [TM + "::test_heal_time_is_applied_detect_plus_heal", TM + "::test_heal_time_drives_downtime_in_a_whole_run"]),
    ("heal: detect time never applied", M, "t + d + h", "t + h", [TM + "::test_heal_time_is_applied_detect_plus_heal"]),
    ("owner: owner-only class heals anyway", M, "    if rng.random() < v[f\"{cls}.p_owner\"]:", "    if False:", [TM + "::test_always_down_owner_only_class_gives_zero", TM + "::test_owner_probability_means_down_to_end_of_night"]),
    ("union: overlapping outages double counted", M, "            cur_e = max(cur_e, e)", "            cur_e = max(cur_e, e)\n            total += e - s", [TM + "::test_heal_time_drives_downtime_in_a_whole_run"]),
    ("election: drop probability ignored", M, "if rng.random() < v[\"election.p_drop\"]:", "if True:", [TM + "::test_election_drop_probability_gates_half_placement"]),
    ("wilson: wrong interval", M, "h = z * math.sqrt(", "h = 0.5 * z * math.sqrt(", [TM + "::test_wilson_known_values"]),
    ("p95: off by one rank", M, "math.ceil(0.95 * len(s)) - 1", "math.ceil(0.95 * len(s))", [TM + "::test_p95_nearest_rank"]),
    ("scenario: fix toggles ignored", P, "+ list(fixes)", "+ []", [TP + "::test_fixes_override_current_and_before_overrides_current", TM + "::test_each_single_fix_does_not_lower_p_full_and_all_three_help"]),
    ("scenario: before state ignored", P, '(["before"] if base == "before" else [])', "[]", [TP + "::test_fixes_override_current_and_before_overrides_current", TM + "::test_before_is_worse_than_current"]),
    ("scenario: fix applied before current", P, 'layers = ["all", "current"] + (["before"] if base == "before" else []) + list(fixes)', 'layers = list(fixes) + ["all", "current"] + (["before"] if base == "before" else [])', [TP + "::test_fixes_override_current_and_before_overrides_current"]),
    ("params: source not required", P, 'for c in COLS if c != "note"', 'for c in ("class", "param")', [TP + "::test_row_without_a_source_is_rejected"]),
    ("seed: draws not reproducible", M, 'random.Random(f"{seed}:{i}:u")', "random.Random()", [TM + "::test_seed_determinism"]),
]


def pytest_rc(tree, tests):
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests],
                           cwd=tree, capture_output=True, timeout=60,
                           env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"})
    except subprocess.TimeoutExpired:
        return 124                                      # a mutant that hangs the tests is caught
    return r.returncode


def fresh(tmp, name):
    dst = pathlib.Path(tmp) / name
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".run-cache.json"))
    return dst


def main():
    killed = 0
    groups = sorted({tuple(m[4]) for m in MUTANTS})
    with tempfile.TemporaryDirectory() as tmp:
        for i, g in enumerate(groups):
            if pytest_rc(fresh(tmp, f"control{i}"), list(g)) != 0:
                print(f"control FAIL {g}"); return 1
        print(f"control {len(groups)}/{len(groups)} test groups pass unmodified")
        for i, (name, f, old, new, tests) in enumerate(MUTANTS):
            tree = fresh(tmp, f"m{i}")
            src = (tree / f).read_text()
            if src.count(old) != 1:
                print(f"mutant {name}: pattern matched {src.count(old)} times, want 1"); return 1
            (tree / f).write_text(src.replace(old, new))
            red = pytest_rc(tree, tests) != 0
            killed += red
            print(f"{'RED ' if red else 'LIVE'} {name}")
    print(f"mutants killed {killed}/{len(MUTANTS)}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
