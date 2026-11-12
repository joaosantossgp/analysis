# Windows registry clock-boundary validation (#489)

The sandbox entity repositories now choose a default system snapshot no earlier
than committed registry timestamps. Explicit historical snapshots are unchanged.
A repeated wall-clock tick can no longer hide an already committed successor.
Conflict detection follows committed evidence rather than reusing an earlier
snapshot timestamp. Corrections also follow attached relationship/lineage
creation boundaries; new edges cannot precede their supporting assertion.

## Evidence

- Baseline `c2c064288a5c3a252b045cf81dcda5b3c99fc653`, Windows build 26200,
  Python 3.11.15: native-clock run had 2 failures / 34 passes.
- Holding both repository clocks at one canonical UTC instant reproduced all
  five issue failures: 5 failed / 31 passed. No arbitrary sleeps were added.
- A separate advancing-then-repeated edge timestamp reproduced historical
  relationship/lineage loss; its two parameterized cases failed before fixing
  assertion closure boundaries. Attaching edges to a newly corrected assertion
  likewise failed before enforcing their supporting assertion's lower bound.
- Final focused suite: **76 passed**, including real/repeated clocks,
  backward-clock repository recreation, replay of the returned system snapshot,
  explicit historical policy selection, graph constraints and existing concurrency cases.
- Full Python/API suite: **1,070 passed, 1 skipped**, 83.65 seconds. Two existing
  dependency deprecation warnings remain. A final focused run after import
  ordering cleanup also passed all 76 cases.
- Protected original data fingerprints remained unchanged in every isolated run.
  Logs and preservation manifests are retained under this worktree's `scratch/`.

## Scope and review

Changed `entity_relationships.py`, `entity_resolution.py` and the shared
`entity_registry_time.py` helper; updated regression tests and the canonical
registry temporal contract. No schema migration, user-data repair, financial
import change, new dependency or registry runtime activation is included.

Ponytail review by the implementing controller: checked caller reachability,
explicit-history behavior, graph write boundaries, conflict handling and the
existing SQLite concurrency tests. Verdict: Ship. This is not an independent
review. These repositories are currently a fresh/sandbox surface with no desktop
or HTTP adapter caller; no packaged UI change or release was tested or published.
Live PostgreSQL execution and large-registry performance were not tested. Default
reads add a maximum-timestamp aggregate over seven registry tables; no new cache,
index or cross-process serialized clock is claimed.
