# Warehouse World Model

**An event-driven, interpretable decision-layer world model for deadline-and-value multi-robot
warehousing.** For each free robot the planner enumerates candidate plans, simulates each one
forward under the fleet's own physics, and commits only the first move — re-planning at every
decision point. The dynamics are *written down* rather than learned (AlphaZero/MPC sense, not
Dreamer), so learning is reserved for what the rules cannot supply.

Against TA-RWARE's own dispatcher, on 144 paired days per regime — the shipped system, rules plus
the self-tuner:

| | wave days | live-stream days |
|---|---|---|
| clean floor | **+21.7%** (t = 9.3) | **+48.8%** (t = 12.2) |
| with disturbances | **+31.6%** (t = 10.9) | **+65.4%** (t = 13.0) |

…while paying an energy cost the baselines skip, at **zero** strandings across 2,300+ runs and
**zero** measured collisions (vertex and swap) over ~96,000 robot-steps per controller.

The project's second half is a set of **negative** results obtained by a value-of-perfect-information
discipline: hand a candidate predictor the true future *before* building it. Six channels came back
null or negative. **Ten mechanisms shipped; twenty-two were measured and cut** against a bar fixed in
advance — see [`docs/ABLATION.md`](docs/ABLATION.md).

- **Paper draft:** [`docs/PAPER_DRAFT.md`](docs/PAPER_DRAFT.md)
- **Interactive sandbox:** explore the floor, race two controllers, and read every measured number
  (built by `scripts/run_race.py`; see *Sandbox* below)
- **Running log:** [`docs/NOTES.md`](docs/NOTES.md) — every experiment, including the ones that failed

---

## Install

```sh
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ./task-assignment-robotic-warehouse --no-deps  # TA-RWARE baseline
.venv/Scripts/python.exe -m pip install -e ./pyastar2d_TARWARE                            # inner-loop A*
.venv/Scripts/python.exe -m pip install -e . --no-deps                                    # wwm_sim (ours)
```

Requires numpy, gymnasium, networkx, matplotlib, pyglet; lightgbm / pandas / scikit-learn for the
(cut) learned heads, and torch only for the MARL baseline in `scripts/marl_dispatch.py`.

## Two simulators

- **`task-assignment-robotic-warehouse/`** — vendored TA-RWARE, left **untouched**. It supplies the
  FIFO dispatcher we benchmark against and the layout/task-rate machinery. Only two packaging fixes
  were made to its `pyproject.toml` so `pip install -e .` succeeds.
- **`wwm_sim/`** — our editable fork, created as a verbatim copy (`tarware` → `wwm_sim`, FIFO parity
  verified) and then extended with the rulebook: battery, deadlines and values, exogenous demand,
  disturbances, partial observability, and the belief map. The rollout engine reuses its rule
  functions on *believed* state.

**The world constants are the result.** §3 of the paper reports a realism audit that reconciled two
contradictory clocks, corrected storage density 31% → 55%, added per-operation service times, and made
demand exogenous. It cut measured throughput by 66% — every pre-audit number in this repo's history
was measured on a world three times too productive, and results dated before 2026-08-06 must not be
cited.

## Reproducing the results

```sh
# head-to-head vs TA-RWARE's dispatcher (1,152 runs; add DISTURB=1 for the hazardous floor)
.venv/Scripts/python.exe scripts/exp_m5_bench.py

# the belief map graded as a probabilistic forecaster (Brier / PR / reliability / latency)
.venv/Scripts/python.exe scripts/exp_m5_brier.py

# safety metrics, measured rather than assumed
.venv/Scripts/python.exe scripts/exp_m5_safety.py

# inner-loop path planner against 1,800 MovingAI MAPF scenarios
.venv/Scripts/python.exe scripts/exp_m5_mapf.py

# the learned opponent: policy-gradient dispatcher, same candidates and features
.venv/Scripts/python.exe scripts/marl_dispatch.py

# every figure in the paper
.venv/Scripts/python.exe scripts/make_paper_figures.py
```

Every `scripts/exp_*.py` is one experiment and prints its own paired statistics. The standing method
rules — 120-seed minimum, two instruments (t and sign), one mechanism at a time, **≥3% or cut**,
validate in the deployment regime — are listed at the end of `docs/TODO.md`.

## Sandbox

```sh
.venv/Scripts/python.exe scripts/race_server.py     # serves the sandbox at :8734 and runs races on demand
.venv/Scripts/python.exe scripts/run_race.py        # one fresh race, then rebuild + open the viewer
```

`results/wwm_sandbox_template.html` is the source; the build substitutes `sim_data.json` and
`races.json` into it. Both the built page and the race library are gitignored as regenerable.

## Repository layout

| path | what |
|---|---|
| `wwm_sim/` | our simulator: warehouse, battery, deadlines, values, demand, disturbances, rumour map |
| `scripts/congestion_policies.py` | the controllers, including the champion stack |
| `scripts/m3_mpc.py` | the model-predictive self-tuner (UCB1 over seven knobs) |
| `scripts/exp_*.py` | one experiment each; the evidence behind every number in the paper |
| `scripts/make_paper_figures.py` | regenerates the paper's figure set from current data |
| `docs/PAPER_DRAFT.md` | the paper |
| `docs/ABLATION.md` | the pre-registered keep/cut ledger |
| `docs/NOTES.md` | the running log — the primary record, including dead ends |
| `docs/ROADMAP.md`, `docs/TODO.md` | milestones with their done-when conditions |
| `data/mapf/` | MovingAI benchmark maps and scenarios |
| `data/instacart/` | hour-of-day × department shares, for the demand-drift calibration |

## Known open items

- **One live-stream day wedges two carriers.** The structural diagnosis (no spare storage) was tested
  and is wrong: supplying slack relocates the wedge to a different seed rather than closing it. The
  audit did find a real bug — the occupancy grid was rebuilt every step, silently restoring pods that
  had been stripped from the charging bays, so a documented world rule had never executed — but
  correcting it hands the vendored baseline a 39-point loss it has no way to avoid, which would
  inflate our margin. Documented, not shipped; see §5.27. The wedge's actual mechanism is unknown.
- **Threshold oscillation** is worth ~7% on stress days, with no forecast involved, and is measured
  but not yet part of the tuner's move set (§5.25).
- **The swap family has not been ported to stock TA-RWARE**, so §5.13's dispatch rules have no
  external-validity check yet.
- **Idle-picker yield** is the last untested liveness rule, and is deliberately deferred: it is the
  first rule that would have to *synthesise* a move rather than gate one, and the residual it targets
  is one 92-step wait per 144 episodes.

## Licence

MIT — see [`LICENSE`](LICENSE), which also records the two vendored MIT projects (TA-RWARE,
pyastar2d) and the terms of the MovingAI and Instacart data.
