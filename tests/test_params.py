import pathlib, pytest
from ringmc import params

HEAD = "class\tparam\tstate\tlow\thigh\tconfidence\tsource\tnote\n"


def write(tmp_path, body):
    p = tmp_path / "p.tsv"
    p.write_text(HEAD + body)
    return p


def test_shipped_file_loads_and_every_row_has_a_source():
    rows = params.load(params.default_path())
    assert len(rows) >= 30
    assert all(r["source"].strip() for r in rows)


def test_row_without_a_source_is_rejected(tmp_path):
    p = write(tmp_path, "poison\trate_per_h\tall\t0.1\t0.5\tESTIMATED\t\tno source\n")
    with pytest.raises(params.ParamError, match="source"):
        params.load(p)


def test_estimated_without_a_range_is_rejected(tmp_path):
    p = write(tmp_path, "poison\trate_per_h\tall\t0.3\t0.3\tESTIMATED\tprivate incident log, finding 1\tx\n")
    with pytest.raises(params.ParamError, match="range"):
        params.load(p)


def test_path_as_source_is_rejected(tmp_path):
    p = write(tmp_path, "poison\trate_per_h\tall\t0.1\t0.5\tESTIMATED\t/some/file.md\tx\n")
    with pytest.raises(params.ParamError, match="path"):
        params.load(p)


def test_bad_confidence_state_and_probability_are_rejected(tmp_path):
    for body, why in [
        ("poison\trate_per_h\tall\t0.1\t0.5\tGUESS\tprivate incident log, finding 1\tx\n", "confidence"),
        ("poison\trate_per_h\tnow\t0.1\t0.5\tESTIMATED\tprivate incident log, finding 1\tx\n", "state"),
        ("poison\tp_owner\tall\t0.1\t1.5\tESTIMATED\tprivate incident log, finding 1\tx\n", "probability"),
    ]:
        with pytest.raises(params.ParamError, match=why):
            params.load(write(tmp_path, body))


def test_fixes_override_current_and_before_overrides_current():
    rows = params.load(params.default_path())
    cur = params.resolve(rows, "current")
    assert cur["wedge.p_owner"] == (1.0, 1.0, "OBSERVED")
    assert params.resolve(rows, "current", ["fix_wedge"])["wedge.p_owner"][:2] == (0.1, 0.5)
    assert params.resolve(rows, "current", ["fix_poison"])["poison.rate_per_h"][:2] == (0.0, 0.05)
    assert params.resolve(rows, "current", ["fix_halfplace"])["half_placement.detect_min"][:2] == (0.3, 1.5)
    assert params.resolve(rows, "before")["poison.rate_per_h"][:2] == (1.0, 1.0)
    assert cur["poison.rate_per_h"][:2] == (0.2, 1.0)


def test_unresolved_required_parameter_is_an_error(tmp_path):
    p = write(tmp_path, "poison\trate_per_h\tall\t0.1\t0.5\tESTIMATED\tprivate incident log, finding 1\tx\n")
    with pytest.raises(params.ParamError, match="unresolved"):
        params.resolve(params.load(p), "current")
