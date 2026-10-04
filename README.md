# ring-reliability-montecarlo

Proves: reliability reasoning under thin evidence. A Monte Carlo model that turns incident-log timings into a probability with an interval, a ranked fix list, and a list of what to measure next. Verify in about 45 s with `./run.sh` (or `make proof`).

Nobody could say how likely a two-node local inference cluster is to serve through an unattended night, or which fix to build next.

## Business problem

A two-machine cluster served one local model. Over one evening the incident log showed several different failures: a master process that exited every hour, probes that collided and reported false alarms, an unprompted master election that dropped a runner, a self-heal that re-placed a healthy cluster, a GPU wedge that needed a person, and a node that fell off the link. Some healed alone in a few minutes. Some waited for an owner. The owner asked two questions: what is the chance the cluster serves from 01:00 to 06:00 with nobody awake, and which open fix buys the most uptime next.

This repo answers both from the logged timings, with the uncertainty shown instead of hidden.

## Run it

```
python3 -m pip install pytest
./run.sh
```

`run.sh` runs three steps and exits 0 only if all pass: `evaluate.py` (scenarios, ranked fixes, tornado), `pytest` (25 tests), and `mutants.py` (14 mutants). Python standard library only, plus pytest. On a laptop it takes about 45 seconds, mostly the 20000-night runs.

## How the model works

1. `params/observed.tsv` holds every input: failure class, parameter, state (before tonight's fixes, current, or one open fix), low, high, a confidence tag, and the source finding. A row with no source, or an ESTIMATED row with no range, is rejected at load. OBSERVED means a number read straight from a timestamped log line. ESTIMATED means a range wide enough to cover the evidence, which is usually one or two events.
2. Each simulated night draws every parameter once from its range (parameter uncertainty), using the same uniform numbers in every scenario so scenarios differ only where their parameters differ.
3. Within a night, failures of each class arrive as a Poisson process. The unprompted election is its own process: each election drops a runner with some probability, and a dropped runner becomes a half-placement outage.
4. Each outage lasts detect time plus heal time, each drawn per event from a gamma distribution with a fixed spread. With probability `p_owner` the event has no self-heal and stays down until 06:00.
5. Overlapping outages merge. A night "serves" when total minutes down are at most 15 and the cluster is up at 06:00. The 15 minute budget is a choice, not a measurement; the budget table below shows how the answer moves.
6. Per scenario: P(serves) with a Wilson 95% interval, mean minutes down, and P95 minutes down. Fix gains use the same nights with and without the fix, so the interval is on the difference.
7. The tornado holds every parameter at its range midpoint and moves one at a time to its low and high end. The widest swings mark what to measure next.

## Reading the result

- Before tonight's fixes a clean night was close to impossible. Current state is far better but still short of a coin flip.
- Ranked by gain in P(serves), deploying the poison-message fix is first. Ranked by minutes saved per night, GPU wedge auto-recover is first, because a wedge costs the rest of the night while a poison exit costs about two minutes. If the goal is "a person is never needed", the wedge fix is the one; if the goal is "no blip inside the budget", it is the poison fix.
- The tornado says the two widest unknowns are the GPU wedge rate and the poison-message rate. One wedge was seen and no poison exit at the hour after the fix landed, so both rates are wide. A week of counted events narrows them more than any new code.

## Results

The "serves" columns depend on the fixed 15 minute budget and on ranges that come from one cluster over a few nights. Output of `python3 evaluate.py`:

Night 01:00 to 06:00 (300 min), 20000 nights per scenario, seed 20261004.
Serves the night = at most 15 min down in total and serving at 06:00. Intervals are Wilson 95%.

| scenario | P(serves the night) | 95% interval | P(no outage at all) | P(down at 06:00) | mean min down | P95 min down |
|---|---|---|---|---|---|---|
| a. before tonight's fixes | 0.3% | 0.3% to 0.4% | 0.0% | 73.7% | 156.8 | 289.5 |
| b. current state | 30.9% | 30.2% to 31.5% | 1.8% | 58.3% | 105.5 | 283.3 |
| c. current + half-placement re-place on first sight | 35.2% | 34.6% to 35.9% | 1.8% | 54.9% | 98.1 | 281.5 |
| c. current + GPU wedge auto-recover | 35.0% | 34.3% to 35.6% | 1.8% | 41.2% | 73.9 | 270.9 |
| c. current + poison-message fix deployed | 42.7% | 42.0% to 43.4% | 19.7% | 54.3% | 95.1 | 281.5 |
| d. current + all three fixes | 58.9% | 58.2% to 59.6% | 19.7% | 30.0% | 51.3 | 257.7 |

How the budget changes the current state (same nights, only the threshold moves).

| minutes down allowed | 5 | 15 | 30 | 60 |
|---|---|---|---|---|
| P(serves the night) | 9.7% | 30.9% | 40.7% | 41.7% |

Open fixes ranked by gain over the current state (same nights in both, so the interval is on the difference).

| rank | fix | P(serves) after | gain | minutes saved per night |
|---|---|---|---|---|
| 1 | poison-message fix deployed | 42.7% | +11.8 pp (+/- 0.5) | 10.4 |
| 2 | half-placement re-place on first sight | 35.2% | +4.4 pp (+/- 0.3) | 7.4 |
| 3 | GPU wedge auto-recover | 35.0% | +4.1 pp (+/- 0.3) | 31.6 |
| all | all three together | 58.9% | +28.1 pp (+/- 0.6) | 54.2 |

Tornado on the current state: every parameter held at its range midpoint (3000 nights per point, midpoint P(serves) 29.7%), one moved to its low then high end.

| rank | parameter | range | P(serves) at low | P(serves) at high | swing |
|---|---|---|---|---|---|
| 1 | wedge.rate_per_h | 0.02 to 0.2 | 46.9% | 18.7% | 28.2 pp |
| 2 | poison.rate_per_h | 0.2 to 1 | 38.6% | 18.8% | 19.9 pp |
| 3 | election.rate_per_h | 0.05 to 0.5 | 37.0% | 23.1% | 13.9 pp |
| 4 | election.p_drop | 0.2 to 0.8 | 35.2% | 25.0% | 10.2 pp |
| 5 | poison.heal_min | 1.5 to 3 | 33.8% | 25.3% | 8.4 pp |
| 6 | node_unreachable.rate_per_h | 0.002 to 0.05 | 33.1% | 25.6% | 7.5 pp |
| 7 | false_stuck.rate_per_h | 0 to 0.05 | 32.0% | 27.6% | 4.5 pp |
| 8 | half_placement.p_owner | 0.05 to 0.3 | 31.8% | 28.0% | 3.8 pp |

## Exact output of `./run.sh`

The pytest line also prints a run time, which differs per machine and is left out here.

```
Night 01:00 to 06:00 (300 min), 20000 nights per scenario, seed 20261004.
Serves the night = at most 15 min down in total and serving at 06:00. Intervals are Wilson 95%.

| scenario | P(serves the night) | 95% interval | P(no outage at all) | P(down at 06:00) | mean min down | P95 min down |
|---|---|---|---|---|---|---|
| a. before tonight's fixes | 0.3% | 0.3% to 0.4% | 0.0% | 73.7% | 156.8 | 289.5 |
| b. current state | 30.9% | 30.2% to 31.5% | 1.8% | 58.3% | 105.5 | 283.3 |
| c. current + half-placement re-place on first sight | 35.2% | 34.6% to 35.9% | 1.8% | 54.9% | 98.1 | 281.5 |
| c. current + GPU wedge auto-recover | 35.0% | 34.3% to 35.6% | 1.8% | 41.2% | 73.9 | 270.9 |
| c. current + poison-message fix deployed | 42.7% | 42.0% to 43.4% | 19.7% | 54.3% | 95.1 | 281.5 |
| d. current + all three fixes | 58.9% | 58.2% to 59.6% | 19.7% | 30.0% | 51.3 | 257.7 |

How the budget changes the current state (same nights, only the threshold moves).

| minutes down allowed | 5 | 15 | 30 | 60 |
|---|---|---|---|---|
| P(serves the night) | 9.7% | 30.9% | 40.7% | 41.7% |

Open fixes ranked by gain over the current state (same nights in both, so the interval is on the difference).

| rank | fix | P(serves) after | gain | minutes saved per night |
|---|---|---|---|---|
| 1 | poison-message fix deployed | 42.7% | +11.8 pp (+/- 0.5) | 10.4 |
| 2 | half-placement re-place on first sight | 35.2% | +4.4 pp (+/- 0.3) | 7.4 |
| 3 | GPU wedge auto-recover | 35.0% | +4.1 pp (+/- 0.3) | 31.6 |
| all | all three together | 58.9% | +28.1 pp (+/- 0.6) | 54.2 |

Tornado on the current state: every parameter held at its range midpoint (3000 nights per point, midpoint P(serves) 29.7%), one moved to its low then high end.

| rank | parameter | range | P(serves) at low | P(serves) at high | swing |
|---|---|---|---|---|---|
| 1 | wedge.rate_per_h | 0.02 to 0.2 | 46.9% | 18.7% | 28.2 pp |
| 2 | poison.rate_per_h | 0.2 to 1 | 38.6% | 18.8% | 19.9 pp |
| 3 | election.rate_per_h | 0.05 to 0.5 | 37.0% | 23.1% | 13.9 pp |
| 4 | election.p_drop | 0.2 to 0.8 | 35.2% | 25.0% | 10.2 pp |
| 5 | poison.heal_min | 1.5 to 3 | 33.8% | 25.3% | 8.4 pp |
| 6 | node_unreachable.rate_per_h | 0.002 to 0.05 | 33.1% | 25.6% | 7.5 pp |
| 7 | false_stuck.rate_per_h | 0 to 0.05 | 32.0% | 27.6% | 4.5 pp |
| 8 | half_placement.p_owner | 0.05 to 0.3 | 31.8% | 28.0% | 3.8 pp |

25 passed

control 14/14 test groups pass unmodified
RED  poisson: rate not converted to per minute
RED  poisson: arrivals run past the night
RED  heal: heal time never applied
RED  heal: detect time never applied
RED  owner: owner-only class heals anyway
RED  union: overlapping outages double counted
RED  election: drop probability ignored
RED  wilson: wrong interval
RED  p95: off by one rank
RED  scenario: fix toggles ignored
RED  scenario: before state ignored
RED  scenario: fix applied before current
RED  params: source not required
RED  seed: draws not reproducible
mutants killed 14/14
```

## Mutants

Each mutant breaks one piece of the model in a scratch copy: Poisson sampling, heal-time or detect-time application, the owner-only path, outage merging, the election drop probability, the interval and percentile maths, the scenario fix toggles and layer order, the source requirement, and seeding. The named tests must go RED. A control run of the same tests on an untouched copy must pass first, so a RED means the code mattered. `mutants.py` fails if any mutant stays alive or any pattern stops matching exactly once.

## Tests that carry the claims

- Same seed gives the same nights; a different seed does not.
- Zero failure rate gives P(serves) of exactly 1.0 and zero minutes down.
- A class that is always down and owner-only gives P(serves) of exactly 0.
- One Poisson class with instant heal: the share of nights with no event sits inside the Wilson interval of exp(-rate x T).
- Mean outage length equals detect plus heal; an owner-only event ends at 06:00.
- The parameter file rejects a row with no source, an ESTIMATED row with no range, a path as a source, a bad state, a probability above 1, and a missing required parameter.
- Every single fix leaves P(serves) no lower, all three together raise it, and the before state is worse than the current state.
- The tornado ranks the parameter that moves the answer and skips fixed values.
- The README tables equal the program output, and no private path or address is in the repo.

## Honesty Statement

The rates come from one private two-node cluster over a few evenings. Most classes were seen once or twice, so most ranges are wide guesses around that evidence, and every guess is tagged ESTIMATED with a low and high. Three values are OBSERVED: the hourly poison rate before the fix, and two owner-needed facts. The model is only as good as these inputs. Nothing here was run against the real cluster; the model reads a table and simulates. The numbers say what the logged evidence allows, not what the cluster will do tonight. Sources are cited as the private incident log and the private wave handoff, by finding or state; those files are not published.

## Limitations

1. One cluster, a few nights. A class seen once has a rate range that spans an order of magnitude. The result moves with those ranges, which is what the tornado shows.
2. The 15 minute budget that defines "serves" is a choice. The budget table shows the effect; the owner's own tolerance should replace it.
3. Poisson arrivals are an approximation. The poison exit looked hourly, not random, and real failures cluster under load.
4. Failures are independent in the model. In the logs a heavy job on the master preceded an election, so load can link several classes. The election rate is where that link sits, and the link itself is a hypothesis.
5. Detect and heal times use one fixed spread (gamma with shape 4). Only a few real recovery times exist: about 2 minutes, 61 seconds, 3 min 59 s, about 10 minutes.
6. The "current" poison rate (0.2 to 1 per hour) is the weakest range: the fix is in code but not deployed, and one expected exit did not happen for a reason not known.
7. The open fixes are modelled by replacing parameter ranges, for example the wedge owner probability falls to 0.1 to 0.5. Those replacement ranges are guesses, because none of the three fixes has run live.
8. Nodes, the network and the model itself are not modelled beyond the seven classes listed in `params/observed.tsv`. Unlisted failure classes make every P(serves) here too high.

## Files

```
params/observed.tsv    every input, with range, confidence tag and source finding
ringmc/params.py       parse, validate, resolve a scenario (base state plus fixes)
ringmc/model.py        Poisson arrivals, outages, merging, summary, Wilson, tornado
evaluate.py            scenario table, ranked fixes, budget table, tornado
mutants.py             the mutation check
tests/                 25 tests
evidence/red-run.txt   the first test run, RED, before the model existed
run.sh, Makefile       the one command
```

## License

MIT, see [LICENSE](LICENSE).
