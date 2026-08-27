# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`autonomy-calc` — a blackout-autonomy calculator (Ukrainian market: power banks,
solar/battery stations, inverter+battery kits, generators). It is a standalone
project; only data and domain experience are carried over from the existing
`autonomy.com.ua` shop, not its code. Primary language of the codebase's
comments, docstrings, commit messages, and `README.md` is Russian/Ukrainian —
match that when editing existing files.

`README.md` is the project's ADR log (37+ entries, `## ADR-NNN. <title>`,
newest at the bottom) — it is the primary source of *why* the code looks the
way it does. Read the relevant ADR before changing a layer's boundary, the
ranking key, or any of the derating constants; don't re-derive from scratch
what's already justified there. `STATUS.md` holds the latest session handoff
(what changed, what's known-broken, what's next) — check it at the start of a
session.

## Commands

```bash
pip install -e ".[dev]"     # install package + dev deps (pytest, mypy, ruff, httpx)
python -m pytest -q         # run the full test suite
python -m pytest tests/test_economics.py::test_name   # single test
python -m mypy              # strict type-check (see [tool.mypy] in pyproject.toml)
ruff check .                # lint
```

`[tool.mypy] strict = true` covers `core reference matching catalog tracking
api tests` — every new module in those packages must pass strict mode, not
just run.

There is no test/lint-runner config beyond `pyproject.toml`; `tests/` is the
only `testpaths` entry and `pythonpath = ["."]` so tests import packages by
their top-level name (`from core.demand import ...`).

Run the API locally with `uvicorn api.app:app --reload` (module `api/app.py`,
`FastAPI(title="autonomy-calc")`).

## Architecture: layered, dependency direction enforced by tests

The codebase is organized as strict layers, and `tests/test_architecture.py`
walks the AST of every file in each package to assert its import roots stay
inside a declared whitelist — this is not a convention, it's a test that
fails the build. When adding an import, check that file first.

```
core/       stdlib only, plus itself. The pure domain: units, load/demand,
            solution-fit evaluation, economics. No pydantic, no yaml, no I/O.
reference/  core + reference + yaml. Curated appliance reference data
            (data/appliances.yaml), not an external-source adapter.
matching/   core + matching only — NOT reference, NOT catalog. The ranking
            engine operates on Candidate structs assembled elsewhere.
catalog/    core + matching + catalog + yaml. The only layer allowed to know
            both core and matching — it's the glue that turns
            products/offers YAML into Candidate for the engine.
tracking/   stdlib only, plus itself. A leaf: click logging knows nothing
            about watt-hours or fitness; the only link to the rest of the
            app is a string offer_id.
api/        everything (core, reference, matching, catalog, tracking,
            fastapi, pydantic) — the outermost layer. Nothing inside the
            other layers may import api/ (checked in both directions:
            test_api_is_the_outermost_layer +
            test_inner_layers_never_import_api). Deleting api/ must not
            break the domain.
```

Rule of thumb baked into the ADRs: `catalog` depends on `matching`, never the
reverse (ADR-021) — the engine must run on candidates assembled from
anywhere (YAML today, a DB later, hand-built in a test).

### Domain flow (core/)

`LoadProfile + AutonomyTarget` → `calculate_requirement()` → `EnergyRequirement`
(demand at the outlet, no battery/inverter knowledge) → `evaluate_fit()` against
a `SolutionSpec` (applies inverter efficiency, DC losses, idle draw, depth of
discharge) → `SolutionFit` (can_run / can_cover_window / blockers / flags) →
`calculate_ownership_cost()` → LCOE (`cost_per_kwh_uah`) and
`payback_energy_kwh`. Requirement calculation and fit evaluation are
deliberately two separate functions (ADR-001) so the core never needs to know
about products, and results are cacheable.

Units are `NewType` wrappers over `float` (`Watt`, `WattHour`, `VoltAmpere`,
`Volt`, `Hours`, ADR-007) — mypy catches unit-mixing (e.g. treating mAh as
Wh) at type-check time, not on-screen. Rounding happens exactly once, when
assembling the final result (ADR-008) — never mid-computation, or golden
tests drift for no real reason.

### Catalog / matching flow

`catalog/products.py` + `catalog/offers.py` (spec vs. price/seller, split
from day one — different lifecycles, ADR-020) load from `data/products.yaml`
and `data/components.yaml` via `*_loader.py`, which also enforce referential
integrity at load time, not at use time (ADR-028). `catalog/candidates.py`
and `catalog/kit_candidates.py` turn `(product, offer)` or compatible
inverter+battery pairs into `matching.Candidate`. `matching/engine.py`
(`select_recommendations`) filters (`can_run` blockers drop the candidate
entirely — ADR-019) and ranks by a lexicographic tuple, never a weighted sum:

```python
key = (coverage, cost_dimension, cost_value, -commission_rate)
```

Commission only breaks ties after coverage and cost already matched
(ADR-018), and `Recommendation` structurally has no `commission_rate` field
at all — it dies inside the engine and never reaches the client (ADR-017,
enforced by `test_recommendation_never_exposes_commission`). `cost_dimension`
exists so a ₴/kWh LCOE value is never compared against a raw ₴ price when one
candidate lacks enough data to compute economics (ADR-029) — mixing the two
silently used to work only because of a three-orders-of-magnitude coincidence.

Inverter/battery compatibility is voltage-*class* with a 15% tolerance
(nominal LiFePO4 cell voltages don't match marketed "12V"/"48V" labels
exactly), not a BMS communication-protocol check — that data doesn't exist in
the catalog (ADR-023). Kits carry a price-weighted average commission
(ADR-024) and their `in_stock` is a conjunction of both halves — no half-kit
is ever shown, since it can't power a load alone.

`explain_rejections()` (matching/, ADR-030) is a second, separate function
run only when `select_recommendations` returns empty (ADR-031) — it explains
"why nothing fit" without touching the primary function's contract. `None`
vs `[]` in the API's `rejected` field distinguishes "diagnosis didn't run"
from "ran and found nothing."

### API / tracking

`api/` is HTTP translation only — `app.py` holds no matching decisions; a
`if kind == GENERATOR: ...` branch belongs in `matching`, not here.
`catalog_provider.py` is the single place in the whole project that knows the
`data/` path (`lru_cache`d load) — swapping in a real DB later touches only
this file. `tracking/` (SQLite-backed click log behind a `ClickLog` Protocol,
ADR-033/034) is injected into the redirect router (`build_router(click_log)`)
rather than imported directly, so tests can substitute an in-memory log.
Click records are append-only by design (no `update`/`delete` on the port) —
an editable attribution log is worthless as evidence in a CPA dispute. `/go`
redirects always `record()` before the 302; a failed write surfaces as a 500
rather than silently sending the user off-site with no attribution.

## Data-integrity conventions worth knowing before editing YAML

- Prefer `measured_wh`/DoD overrides on a specific product over the class
  default whenever a real measurement or datasheet value exists — the
  override is surfaced via a flag (`USED_MEASURED_CAPACITY`,
  `USED_PRODUCT_DOD_OVERRIDE`), never silently absorbed (ADR-006, ADR-025).
- Any number that lands in the catalog must be checked line-by-line against
  an independent source (manufacturer/seller page) — matching a list of file
  names or eyeballing a table is not verification (ADR-026 records a real
  column-shift bug caught this way).
- If a device has modes or models differing by more than ~30%, that's
  separate reference entries, not one averaged number (ADR-016).
- An offer with no `url` must 404 on `/go`, not redirect anywhere, and must
  not be recorded as a click (ADR-034). Filling in real seller URLs is an
  ongoing data task, not a code task.
- Data-quality provenance metadata (e.g. `fuel_rate_source`) lives in the
  catalog layer next to the spec, never inside `core`'s domain types — the
  physics doesn't change based on how trustworthy the input number is
  (ADR-013, ADR-027).
