"""Run every scenario, rank the open fixes, build the tornado table. Prints the text the README embeds."""
import hashlib, json, pathlib, sys
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from ringmc import model, params

N = 20000
N_TORNADO = 3000
SEED = 20261004
CACHE = HERE / ".run-cache.json"
BUDGETS = (5, 15, 30, 60)
FIXES = [("fix_halfplace", "half-placement re-place on first sight"),
         ("fix_wedge", "GPU wedge auto-recover"),
         ("fix_poison", "poison-message fix deployed")]


def source_hash():
    h = hashlib.sha256()
    for f in sorted(HERE.glob("ringmc/*.py")) + [HERE / "evaluate.py", params.default_path()]:
        h.update(f.read_bytes())
    return h.hexdigest()


def pct(x):
    return f"{100 * x:.1f}%"


def rng_txt(lo, hi):
    return f"{lo:g} to {hi:g}"


def results(n=N, n_tornado=N_TORNADO):
    rows = params.load(params.default_path())
    scen = [("a. before tonight's fixes", "before", []), ("b. current state", "current", [])]
    scen += [(f"c. current + {d}", "current", [f]) for f, d in FIXES]
    scen.append(("d. current + all three fixes", "current", [f for f, _ in FIXES]))
    runs = {}
    for name, base, fx in scen:
        runs[name] = model.simulate(params.resolve(rows, base, fx), n, SEED)
    base = runs["b. current state"]
    out = [f"Night 01:00 to 06:00 (300 min), {n} nights per scenario, seed {SEED}.",
           f"Serves the night = at most {model.BUDGET_MIN:g} min down in total and serving at 06:00. Intervals are Wilson 95%.",
           "", "| scenario | P(serves the night) | 95% interval | P(no outage at all) | P(down at 06:00) | mean min down | P95 min down |",
           "|---|---|---|---|---|---|---|"]
    for name, _, _ in scen:
        s = model.summarize(runs[name])
        lo, hi = s["p_full_ci"]
        out.append(f"| {name} | {pct(s['p_full'])} | {pct(lo)} to {pct(hi)} | {pct(s['p_clean'])} | {pct(s['p_stall'])} | "
                   f"{s['mean_down']:.1f} | {s['p95_down']:.1f} |")
    out += ["", "How the budget changes the current state (same nights, only the threshold moves).", "",
            "| minutes down allowed | " + " | ".join(f"{b:g}" for b in BUDGETS) + " |", "|---|" + "---|" * len(BUDGETS),
            "| P(serves the night) | " + " | ".join(pct(sum(model.serves(r, b) for r in base) / n) for b in BUDGETS) + " |"]
    ranked = []
    for (name, _, fx), (f, d) in zip(scen[2:5], FIXES):
        g, hw, mins = model.paired_gain(base, runs[name])
        ranked.append((g, d, model.summarize(runs[name])["p_full"], hw, mins))
    ranked.sort(key=lambda r: -r[0])
    out += ["", "Open fixes ranked by gain over the current state (same nights in both, so the interval is on the difference).", "",
            "| rank | fix | P(serves) after | gain | minutes saved per night |", "|---|---|---|---|---|"]
    for i, (g, d, p, hw, mins) in enumerate(ranked, 1):
        out.append(f"| {i} | {d} | {pct(p)} | {100 * g:+.1f} pp (+/- {100 * hw:.1f}) | {mins:.1f} |")
    g, hw, mins = model.paired_gain(base, runs["d. current + all three fixes"])
    out.append(f"| all | all three together | {pct(model.summarize(runs['d. current + all three fixes'])['p_full'])} | "
               f"{100 * g:+.1f} pp (+/- {100 * hw:.1f}) | {mins:.1f} |")
    cur = params.resolve(rows, "current")
    tor = model.tornado(cur, n_tornado, SEED)
    out += ["", f"Tornado on the current state: every parameter held at its range midpoint ({n_tornado} nights per point, "
                f"midpoint P(serves) {pct(tor[0]['p_mid'])}), one moved to its low then high end.", "",
            "| rank | parameter | range | P(serves) at low | P(serves) at high | swing |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(tor[:8], 1):
        out.append(f"| {i} | {r['key']} | {rng_txt(r['low'], r['high'])} | {pct(r['p_at_low'])} | {pct(r['p_at_high'])} | "
                   f"{100 * r['swing']:.1f} pp |")
    out += ["", f"Ring failure classes injected at random ({n} nights, parameters drawn per night). Recovered = back before 06:00 with no owner step; "
                "each cell is recovered/injected.", "", "| class | current state | current + all three fixes |", "|---|---|---|"]
    fixed = params.resolve(rows, "current", [f for f, _ in FIXES])
    rc, rf = model.recovery_totals(cur, n, SEED), model.recovery_totals(fixed, n, SEED)
    out += [f"| {k} | {rc[k][1]}/{rc[k][0]} | {rf[k][1]}/{rf[k][0]} |" for k, _ in model.INJECTED]
    return "\n".join(out)


def cached():
    key = source_hash()
    try:
        c = json.loads(CACHE.read_text())
        if c.get("key") == key:
            return c["text"]
    except (OSError, ValueError, KeyError):
        pass
    text = results()
    try:
        CACHE.write_text(json.dumps({"key": key, "text": text}))
    except OSError:
        pass
    return text


if __name__ == "__main__":
    print(cached())
