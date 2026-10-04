"""Discrete-event Monte Carlo of one unattended night. Standard library only."""
import math
import random

NIGHT_MIN = 300.0          # 01:00 to 06:00
BUDGET_MIN = 15.0          # "serves the night" = at most this many minutes down and serving at 06:00
SHAPE = 4.0                # per-event spread of detect and heal times (gamma, coefficient of variation 0.5)
RATE_CLASSES = ("poison", "probe_collision", "false_stuck", "wedge", "node_unreachable")
FOUR = ("rate_per_h", "detect_min", "heal_min", "p_owner")
KEYS = sorted([f"{c}.{p}" for c in RATE_CLASSES for p in FOUR]
              + ["election.rate_per_h", "election.p_drop", "half_placement.detect_min",
                 "half_placement.heal_min", "half_placement.p_owner"])


def zero_ranges():
    return {k: (0.0, 0.0, "ESTIMATED") for k in KEYS}


def arrivals(rng, rate_per_h, horizon=NIGHT_MIN):
    """Poisson arrival times in minutes."""
    out = []
    if rate_per_h <= 0:
        return out
    t = 0.0
    while True:
        t += rng.expovariate(rate_per_h / 60.0)
        if t >= horizon:
            return out
        out.append(t)


def _dur(rng, mean):
    return 0.0 if mean <= 0 else mean * rng.gammavariate(SHAPE, 1.0 / SHAPE)


def outage_end(rng, v, cls, t):
    """Minute at which an outage that starts at t ends. An owner-only event never ends before 06:00."""
    if rng.random() < v[f"{cls}.p_owner"]:
        return NIGHT_MIN
    d = _dur(rng, v[f"{cls}.detect_min"])
    h = _dur(rng, v[f"{cls}.heal_min"])
    return min(NIGHT_MIN, t + d + h)


def union_minutes(intervals):
    total, cur_s, cur_e = 0.0, None, None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def run_once(v, seed, i):
    """One night. Returns (down_minutes, outage_events, still_down_at_end)."""
    iv = []
    for cls in RATE_CLASSES:
        rng = random.Random(f"{seed}:{i}:{cls}")
        for t in arrivals(rng, v[f"{cls}.rate_per_h"]):
            iv.append((t, outage_end(rng, v, cls, t)))
    rng = random.Random(f"{seed}:{i}:election")
    for t in arrivals(rng, v["election.rate_per_h"]):
        if rng.random() < v["election.p_drop"]:
            iv.append((t, outage_end(rng, v, "half_placement", t)))
    return union_minutes(iv), len(iv), any(e >= NIGHT_MIN for _, e in iv)


def simulate(ranges, n, seed, values=None):
    """n nights. Each night draws every parameter once from its range (parameter uncertainty), or takes
    `values` as fixed numbers. Parameter draws use the same uniform numbers in every scenario."""
    out = []
    for i in range(n):
        if values is not None:
            v = values
        else:
            u = random.Random(f"{seed}:{i}:u")
            v = {}
            for k in KEYS:
                lo, hi = ranges[k][0], ranges[k][1]
                v[k] = lo + u.random() * (hi - lo)
        out.append(run_once(v, seed, i))
    return out


def wilson(k, n, z=1.959964):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def percentile95(xs):
    s = sorted(xs)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def serves(run, budget=BUDGET_MIN):
    return run[0] <= budget and not run[2]


def summarize(runs):
    n = len(runs)
    full = sum(1 for r in runs if serves(r))
    clean = sum(1 for r in runs if r[1] == 0)
    downs = [r[0] for r in runs]
    return {"n": n, "p_full": full / n, "p_full_ci": wilson(full, n), "p_clean": clean / n,
            "p_clean_ci": wilson(clean, n), "p_stall": sum(1 for r in runs if r[2]) / n, "mean_down": sum(downs) / n, "p95_down": percentile95(downs)}


def paired_gain(base_runs, fix_runs):
    """Gain in P(full night) and mean minutes saved, same nights in both. Returns (gain, half_width_95, minutes)."""
    n = len(base_runs)
    d = [(1 if serves(f) else 0) - (1 if serves(b) else 0) for b, f in zip(base_runs, fix_runs)]
    m = sum(d) / n
    var = sum((x - m) ** 2 for x in d) / (n - 1)
    mins = sum(b[0] - f[0] for b, f in zip(base_runs, fix_runs)) / n
    return m, 1.959964 * math.sqrt(var / n), mins


def tornado(ranges, n, seed):
    """Hold every parameter at its range midpoint, move one to its low then its high end. Rows sorted by swing."""
    mid = {k: (ranges[k][0] + ranges[k][1]) / 2 for k in KEYS}
    p_mid = summarize(simulate(ranges, n, seed, values=mid))["p_full"]
    rows = []
    for k in KEYS:
        lo, hi = ranges[k][0], ranges[k][1]
        if lo == hi:
            continue
        res = []
        for x in (lo, hi):
            res.append(summarize(simulate(ranges, n, seed, values=dict(mid, **{k: x})))["p_full"])
        rows.append({"key": k, "low": lo, "high": hi, "p_at_low": res[0], "p_at_high": res[1],
                     "swing": abs(res[1] - res[0]), "p_mid": p_mid})
    rows.sort(key=lambda r: (-r["swing"], r["key"]))
    return rows
