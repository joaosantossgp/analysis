# CVMAnalytics

A local-first analyst workbench for Brazilian listed companies. Its data comes
from official CVM filings and is stored and read on the analyst's machine.

## Language

### Local data

**Local database**:
All company data stored on the analyst's machine. It stays readable offline.
_Avoid_: base, the database (unqualified), cache

**Data update**:
An explicit, logged run that fetches official CVM filings into the local
database. It is never started implicitly by opening a screen.
_Avoid_: Database Updates, Data Updates, Update Database, Update Base, sync

**Company update**:
A data update limited to a single company.
_Avoid_: on-demand refresh, Update data (for this scope)

**Stale**:
The state of the local database when a CVM filing deadline (ITR or DFP) has
passed since the last successful data update covering all active companies, so
newer filings may exist. Company updates and retries do not reset it.
_Avoid_: outdated, old, out of sync

**History range**:
The span of past fiscal years that a data update fetches.
_Avoid_: period (reserved for statement periods), year range, window

**Data completeness**:
Whether the local database holds usable statements for a given company and
period.
_Avoid_: coverage (for this meaning), health, gaps

### Analyst work

**Coverage universe**:
The set of companies an analyst has chosen to cover.
_Avoid_: universe (for the set of companies a data update fetches), preset
