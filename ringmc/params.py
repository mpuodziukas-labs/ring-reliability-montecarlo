"""Parameter file: parse, validate, and resolve per scenario."""
import csv
import pathlib

CONF = {"OBSERVED", "ESTIMATED"}
STATES = {"all", "before", "current", "fix_poison", "fix_halfplace", "fix_wedge"}
COLS = ["class", "param", "state", "low", "high", "confidence", "source", "note"]
FOUR = ("rate_per_h", "detect_min", "heal_min", "p_owner")
REQUIRED = (
    [f"{c}.{p}" for c in ("poison", "probe_collision", "false_stuck", "wedge", "node_unreachable") for p in FOUR]
    + ["election.rate_per_h", "election.p_drop", "half_placement.detect_min", "half_placement.heal_min",
       "half_placement.p_owner"]
)


class ParamError(ValueError):
    pass


def load(path):
    rows = []
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        if rd.fieldnames != COLS:
            raise ParamError(f"header must be {COLS}, got {rd.fieldnames}")
        for n, r in enumerate(rd, start=2):
            where = f"row {n}"
            if any(r[c] is None or not r[c].strip() for c in COLS if c != "note"):
                raise ParamError(f"{where}: empty field (every row needs a source)")
            if "/" in r["source"]:
                raise ParamError(f"{where}: source must cite a finding, not a path")
            if r["confidence"] not in CONF:
                raise ParamError(f"{where}: confidence must be OBSERVED or ESTIMATED")
            if r["state"] not in STATES:
                raise ParamError(f"{where}: unknown state {r['state']}")
            try:
                lo, hi = float(r["low"]), float(r["high"])
            except ValueError:
                raise ParamError(f"{where}: low/high must be numbers")
            if lo < 0 or hi < lo:
                raise ParamError(f"{where}: need 0 <= low <= high")
            if r["param"].startswith("p_") and hi > 1:
                raise ParamError(f"{where}: probability above 1")
            if r["confidence"] == "ESTIMATED" and not lo < hi:
                raise ParamError(f"{where}: ESTIMATED needs a low/high range")
            if r["confidence"] == "OBSERVED" and lo != hi:
                raise ParamError(f"{where}: OBSERVED is a single value")
            rows.append({"key": f"{r['class']}.{r['param']}", "state": r["state"], "low": lo, "high": hi,
                         "conf": r["confidence"], "source": r["source"]})
    return rows


def resolve(rows, base, fixes=()):
    """Layers: all, current, (before if base is 'before'), then each fix. Later layers win."""
    layers = ["all", "current"] + (["before"] if base == "before" else []) + list(fixes)
    out = {}
    for layer in layers:
        for r in rows:
            if r["state"] == layer:
                out[r["key"]] = (r["low"], r["high"], r["conf"])
    missing = [k for k in REQUIRED if k not in out]
    if missing:
        raise ParamError(f"unresolved parameters: {missing}")
    return out


def default_path():
    return pathlib.Path(__file__).resolve().parent.parent / "params" / "observed.tsv"
