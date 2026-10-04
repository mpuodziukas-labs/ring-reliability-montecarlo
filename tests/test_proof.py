import pathlib, re
import evaluate, mutants

ROOT = pathlib.Path(__file__).parent.parent
README = (ROOT / "README.md").read_text()


def test_readme_results_match_evaluate_output():
    assert evaluate.cached() in README, "README results drifted from evaluate.py"


def test_readme_lists_every_mutant_and_the_count():
    for name, *_ in mutants.MUTANTS:
        assert f"RED  {name}" in README, f"README misses mutant: {name}"
    assert f"mutants killed {len(mutants.MUTANTS)}/{len(mutants.MUTANTS)}" in README


def test_every_mutant_pattern_exists_exactly_once_and_names_real_tests():
    for name, f, old, new, tests in mutants.MUTANTS:
        assert (ROOT / f).read_text().count(old) == 1, name
        for t in tests:
            path, _, fn = t.partition("::")
            assert fn in (ROOT / path).read_text(), name


def test_no_private_paths_or_hosts_in_the_repo():
    parts = ["/Us" + "ers/", "/ho" + "me/[a-z]", "Obsi" + "dian", r"192\.168\.", r"\b10\.\d+\.\d+\.\d+\b", r"\.lo" + "cal", ":52" + "415"]
    bad = re.compile("|".join(parts))
    files = [f for f in ROOT.glob("**/*") if f.suffix in (".py", ".md", ".tsv", ".sh", ".txt") and ".git" not in f.parts]
    assert len(files) >= 10
    for f in files:
        if f.name == "test_proof.py":
            continue
        assert not bad.search(f.read_text()), f
