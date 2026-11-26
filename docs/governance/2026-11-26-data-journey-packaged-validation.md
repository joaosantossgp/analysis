# Packaged validation of the new data journey — #550

Date: 2026-11-26. Scope: the shell-owned data update delivered by goal
[#539](https://github.com/joaosantossgp/analysis/issues/539) (ADR 0010).
**The journey works end to end in the packaged app, but six bugs were found and
filed (#575-#580). One of them breaks offline reads after a mid-session network
drop.** This is targeted local validation, not release acceptance or
publication.

**Re-check (same day, after #595-#600): all six pass in a new packaged build.**
See [Packaged re-check after the fixes](#packaged-re-check-after-the-fixes).

## Artifact identity

| Field | Observed value |
|---|---|
| Source commit | `26826c5` (`origin/main`, merge of #573), tracked-clean before build |
| Build command | `desktop/build_desktop.ps1` with the project `.venv/Scripts` first on PATH; 84 s |
| Runtime | `0.30.0-rc.1-222-g26826c5`, build `26826c5`, built `2026-11-26T14:09:23Z` |
| Shell | Frozen Python, Vite, pywebview/WebView2; bridge ready |
| Executable | `dist/CVMAnalytics/CVMAnalytics.exe`, 23,189,225 bytes |
| EXE SHA-256 | `2c9495eb4f298d069861044e50706a835ee2ca2bad67ad04379dedb121f86d2d` |
| Bundle | 1,556 files, 282,093,264 bytes; no `.db`, `.sqlite` or `.sqlite3` files |
| Bundle manifest SHA-256 | `7477009035b7a547d0d09f52d4af6bf93fbe77b9d3dfe43630be26075027061f` (lines `<sha256> <relative-path>`, sorted by path) |
| Host | Windows 11 Pro build 26200 |

The build rewrites `desktop/__version__.py`; that change was reverted and is
not part of this PR. No tag or release was made.

## Isolation and method

Each run used a fresh data root under `tmp/550/<run>/fixture`, never
`%USERPROFILE%\Documents\CVMAnalytics`. The launcher set `CVMANALYTICS_DATA_DIR`,
`CVM_DATA_DIR` and the explicit database, input, metadata, output, reports,
logs, cache, energy, news and onboarding paths inside the fixture. It pointed
`LOCALAPPDATA` at a sibling test profile, **unset `DATABASE_URL` and
`TEST_DATABASE_URL`**, and refused to start if either was still set. Settings ->
App confirmed every path inside the fixture.

A throwaway Playwright driver connected to WebView2 over CDP
(`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=…`). It clicked
the real UI and read the real bridge (`get_local_database_state`,
`check_update`, `get_companies`). It took screenshots and saved page text. The
bundled Python was not patched or mocked. GUI interaction was programmatic
clicks and key presses, not a human at the window.

**Offline runs** set `HTTP(S)_PROXY`/`ALL_PROXY` and WebView2's `--proxy-server`
to the dead loopback `127.0.0.1:9`, with only `127.0.0.1;localhost` bypassed.
`CVM_CATALOG_URL` pointed there too. All external traffic from Python and the
WebView failed, while the app's own loopback server kept working. The
browser connectivity flag was emulated in the page: `navigator.onLine` was
forced false before the app's scripts ran ("launched offline"), or forced false
with a dispatched `offline` event ("connection lost mid-session"). CDP's own
network-offline emulation was tried first and discarded: it also blocks the
app's loopback asset server, so lazy route chunks fail to load. That is an
artifact real offline Windows does not produce. **The network adapter was not
disabled**, so this is not a packet-level offline test.

## Online journey (fresh data root)

Timeline in UTC (launch 14:10:51):

| Time | Observation | Result |
|---|---|---|
| 14:10:57 | First launch: state `empty`; pill `○ EMPTY`; Home hero "No CVM data on this computer yet" with one primary "Download CVM data" and "Official CVM · DFP, ITR · every active company"; Completeness and Gaps show `—`; Companies and Sectors empty states offer the same action; the Data panel says "Data updates run only when you start them". No download ran before the click. | Pass, but the pill and hero only appear 30 s after load (#576) |
| 14:12:06 | Clicked "Download CVM data" on Home. Pill `↻ STARTING`, then `CVM FILES 3/10`. Scope `data_update`, 655 companies queued. | Pass |
| ≤14:12:35 | File phase finished (10 files, under 29 s). Phase `companies`. | Pass |
| 14:12:35-14:12:58 | First company stored (at most 52 s after the click); `has_statements: true`; pill `UPDATING 0%`. | Pass |
| 14:13:22 | `get_companies` returned the catalog rows, but the open Companies page still showed "0 companies". Rows appeared only after navigating away and back, as `◌ Queued`, with the status line "Data update running · 7 of 655 companies processed". | Fail (#577) |
| 14:14:35 | AMBEV (23264) Financial Statements readable: DRE, 13 periods, 38 rows, source "Official CVM filings · Local database copy", while the run continued. | Pass |
| 14:16:06 | Petrobras (9512, still queued) offered "Download now". The click started a company update beside the running data update; it succeeded at 14:17:37 with 5,866 rows. Its inline status includes Portuguese text ("Solicitacao enfileirada para processamento interno."). | Pass; existing language debt |
| 14:17:50-14:20:24 | BIOMM (19305) stayed `Queued` in the open directory 150 s after the bridge returned it with 4,816 rows. | Fail (#577) |
| Throughout | Data panel ETA: "About 4 min left" at 7/655, "Under a minute left" at 20/655, `eta_seconds` 6-118 s. Real pace was about 10.3 s per company (33 → 48 in 154 s), about 1 h 52 min for 655. | Fail (#578) |
| 14:13:30, 14:20:38 | Home had dropped the hero once the first company landed and showed "START WITH A COMPANY" for the rest of the first run. | Fail (#579) |
| 14:20:39 | "Cancel update" in the Data panel. Job `cancelled` at 14:20:44 with 51 of 655 processed and 0 failures. The button showed no "Cancelling" state in between. | Pass |
| 14:21:12 | State `stale`, pill `▲ STALE`, panel and Home notice "New CVM filings may be due · No full data update has been recorded yet", primary "Update data". | Pass (a cancelled run is not a full data update) |
| Before 14:21:58 | Window closed with `CloseMainWindow`; process exited within 20 s. The 14:21:58 relaunch (offline run below) read the same state (`stale`, last run `cancelled`), not `interrupted`. | Pass |

The launch GICS sync logged `{'skipped_unchanged': 1}` on relaunch (#548).
No console errors were recorded while the driver was attached during the online run.

**Storage:** after 52 stored companies, `cvm_financials.db` was 1,338,187,776
bytes (about 25.7 MB per company), and raw DFP/ITR inputs were 2,459,410,525
bytes. A linear projection for 655 companies is about 16.8 GB, above the 12 GiB
single-database budget. This is unverified (the run was not completed) and was
added to [#574](https://github.com/joaosantossgp/analysis/issues/574).

## Offline journeys

| Scenario | Observation | Result |
|---|---|---|
| Launched offline, populated (52 companies, after cancel) | Pill `▲ STALE · OFFLINE`; Home notice and panel append "No internet connection"; "Update data" disabled with "Offline — connect to download."; Companies lists 655; AMBEV statements readable (13 periods); Petrobras overview readable; Sectors "12 groups · 655 companies". | Pass |
| Update check, offline | Settings -> Advanced -> Software update: "Update check failed", latest "unknown", "Could not check GitHub Releases. Check your internet connection or try again later." Bridge `check_update.status = check_failed`. | Pass |
| Update check, online | "Up to date", latest `0.29.2` (`releases/latest` excludes the `0.30.0-rc.1` prerelease). | Pass |
| Connection lost mid-session | After the `offline` event: Companies stuck on "LOADING DIRECTORY…" for 40 s, the company page on "LOADING COMPANY DATA…", and BIOMM statements report "NO LOCAL STATEMENT EVIDENCE" despite 4,816 stored rows. Dispatching `online` recovered 655 companies within 3 s. | **Fail (#575)** |
| Launched offline, empty data root | Pill `○ EMPTY · OFFLINE`; hero "No CVM data on this computer yet … · No internet connection."; "Download CVM data" disabled with "Offline — connect to download." on Home, the panel, Companies and Sectors. No crash. | Pass |
| Empty data root, browser online but CVM unreachable | Click shows "Catalog refresh failed. The previous local snapshot has been preserved." under the clicked button only; pill and panel stay `EMPTY`, no Failed state, no retry. | Fail (#580) |

## Not validated

- **Full first run to completion**, and therefore the "Up to date" state, the
  final first-run duration, and the end-of-run completeness recompute. A full
  run is about 2 hours today ([#574](https://github.com/joaosantossgp/analysis/issues/574)).
- **"Completed with N failures" and per-company retry**: no company failed among
  the 51 processed, and no cheap way to force a failure was found without
  patching the bundle. The bridge tests cover these states; the packaged UI does not.
- **"Failed" state from a failed file download** inside a running job. The CVM
  files downloaded cleanly; the unreachable-catalog case fails before a job exists (#580).
- **Packet-level offline** (adapter disabled) and the browser's own
  `navigator.onLine` transitions; both were emulated as described above.
- Laptop-width layout, Excel export, install/update over a previous version,
  and the updater apply path were out of scope for this issue.

## Observations not filed

- Settings -> App shows "DATA ROOT MODE: shared Documents data" even when
  `CVMANALYTICS_DATA_DIR` points elsewhere; the listed paths were correct.
- `desktop/updater.py` queries `joaosantossgp/analisys` (the pre-rename slug).
  It works through GitHub's rename redirect today.
- The Data panel stays open across route changes and covers part of the
  company header actions; the first outside click only closes it.

## Reproduction

Build the source above with the canonical builder. The local driver
`tmp/550/cdp.cjs` and launcher `tmp/550/launch.sh` are throwaway and not
committed. The launcher's child environment matches the
[#479 recipe](2026-11-06-packaged-storage-validation.md#reproduction) plus
`unset DATABASE_URL TEST_DATABASE_URL`. Proxy variables are set only for
offline runs, and the CDP port is in `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`.
Run `bash tmp/550/launch.sh <fixture> <port> [offline]`, then
`node tmp/550/cdp.cjs <port> <outdir> <actions…>`; actions include `state`,
`shot:<name>:<hash-route>`, `click:<button text>`, `panel`, `launchoffline`,
`dropnet`, `restorenet`, `timeload` and `wait:<s>`.

## Local evidence

Raw evidence stays local under `tmp/550/` (screenshots, page text, bridge
payloads, fixture databases and logs) and `tmp/build-550.log`. It is not
committed or published.

| Local evidence file | SHA-256 |
|---|---|
| `online/driver.jsonl` | `8981ca017af05417bdc1809cf1a9c85ea73a747aab4aa9c8d5d94b6b3e5a0850` |
| `offline-data/launch/driver.jsonl` | `54d30da8cf186d9a1a57c0a066bf63ca2552d943521d3714d5b5f6f902faa87a` |
| `offline-data/midsession/driver.jsonl` | `c38e98b319719feebb68c58ba52d0ed34f1ba9dc21e9480a3978ad0c92d06f49` |
| `offline-empty/driver.jsonl` | `48953c3dded18a9b040f25801cc9893c99546a0f2f6adae9aa8316ce82896ba3` |
| `offline-empty/unreachable/driver.jsonl` | `a063b276ec4b7825513ba7cb7e715bf14b76e3e0b400ca9d4ae1b98766142cd2` |
| `cdp.cjs` | `1547132b8a9cceaa95eac42d552330df48e33d66178e2c867f1372c9a43fab2d` |
| `launch.sh` | `7c19f1c7bbe7bdd1804ba5d65d7bb82fe78376250557c0770e3b7307b9046999` |

## Bugs filed

| Issue | Failure |
|---|---|
| [#575](https://github.com/joaosantossgp/analysis/issues/575) | Offline mid-session: bridge reads pause and downloaded data looks missing |
| [#576](https://github.com/joaosantossgp/analysis/issues/576) | Local database pill and empty-database hero appear only after 30 s on every launch |
| [#577](https://github.com/joaosantossgp/analysis/issues/577) | Companies directory does not refresh during a data update |
| [#578](https://github.com/joaosantossgp/analysis/issues/578) | Data update ETA uses time in the current stage |
| [#579](https://github.com/joaosantossgp/analysis/issues/579) | Home hero disappears after the first company lands during the first data update |
| [#580](https://github.com/joaosantossgp/analysis/issues/580) | Data update that cannot reach CVM shows a misleading inline error and no Failed state |

## Packaged re-check after the fixes

A second packaged build re-checked the six failures after their fixes merged
(#595, #596, #597, #598, #599, #600; #574's first-run cost work was already on `main`).

| Field | Observed value |
|---|---|
| Source commit | `0378696` (`origin/main`, merge of #600), tracked-clean before build |
| Build command | `desktop/build_desktop.ps1` with the project `.venv/Scripts` first on PATH; 50 s |
| Runtime | `0.30.0-rc.1-254-g0378696`, built `2026-11-26T21:35:36Z` |
| Executable | `dist/CVMAnalytics/CVMAnalytics.exe`, 23,191,144 bytes |
| EXE SHA-256 | `20c99c59af19482df10f6661721730bb5cfd22f129526fd868f7ade46c732f19` |
| Bundle | 1,558 files, 282,098,938 bytes; no `.db`, `.sqlite` or `.sqlite3` files |
| Bundle manifest SHA-256 | `e2ac695a1d0b386349feed58874d516e2eb85295f1c7fc548131d2b4b487ade7` (same line format as above) |

The build's `desktop/__version__.py` rewrite was reverted. Isolation followed the
method above: the
[#479 recipe](2026-11-06-packaged-storage-validation.md#reproduction)
environment with every data path in a fresh `fixture`, `LOCALAPPDATA` in a
sibling directory, `DATABASE_URL`/`TEST_DATABASE_URL` unset, and the CDP port in
`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`. The fixture database was created on
first launch. The modification time of the real
`%USERPROFILE%\Documents\CVMAnalytics\db\cvm_financials.db` was the same before and
after (`2026-11-26T19:13:38Z`). A throwaway Node CDP driver clicked the real UI
and read the real bridge, as before. The "connection lost" and "CVM unreachable"
cases used the same emulation as the original runs.

| Issue | Re-check | Result |
|---|---|---|
| #576 | Fresh fixture, page reloaded twice: bridge ready 103-104 ms, pill 103-104 ms, empty hero 428-436 ms (was 30.1 s). | Pass |
| #579 | Clicked "Download CVM data" on Home at 21:37:58 UTC. `has_statements` was true from about 30 s; at 30-81 s with 0-10 of 655 processed, Home still showed the "Getting CVM data" hero and never "Start with a company". | Pass |
| #577 | Companies opened at 90 s during the run: "655 companies", 25 rows. Queued rows fell 25 → 11 by 310 s while the page stayed open. Six row-by-row checks (80-86 processed) compared every Queued row with `get_companies`: no row was Queued while the bridge already reported data. | Pass |
| #578 | `eta_seconds` against the pace measured from the samples: 3,735 vs 3,265 at 13/655; 2,825 vs 2,631 at 29/655; 2,644 vs 2,566 at 65/655 (about 44 vs 43 min). Previously "Under a minute left" at 20/655. | Pass |
| #575 | Run cancelled at 91 of 655 (state `stale`). Then `navigator.onLine` was forced false and `offline` dispatched. Pill showed `STALE · OFFLINE`. Companies listed 655 with no loading banner. Company 25283 (AERIS) opened. Its Financial Statements showed "DRE · 13 periods · 31 rows", not "No local statement evidence". | Pass |
| #580 | Fresh fixture, dead proxy, browser online. Clicked "Download CVM data". After 20 s: state `failed`, pill "Data update failed", Home "The download didn't finish" with "Could not reach CVM to get the company list. Nothing was downloaded.", action "Try again". Companies also offered "Try again". No "previous local snapshot" copy anywhere. | Pass |

Still not validated: a full first run to completion in the packaged app, packet-level
offline, and the other items listed under [Not validated](#not-validated).

Local evidence stays outside the repository (session scratch directory), not committed:

| Local evidence file | SHA-256 |
|---|---|
| `online/run.jsonl` | `aa7ee0504a7fedbe9e9ea47fc03d697976445caeee8f2f32da137cd2e4c46b09` |
| `online/rows.jsonl` | `e704d11c942ca047904a61aaeb0ec3b632e4b85f9f9f3b4527335e6ea7c2566a` |
| `online/dropnet.jsonl` | `d4c1f7c18dfc1d50a03f50d91bfeb26cd07fd02b4fd88ef9f6eef3da0c5c7945` |
| `unreachable/driver.jsonl` | `c1f7ff95e6fd5cba9225afbecc93c6f6e0836e6434e9b6dfe148f69de5c210ca` |
| `drive.mjs` | `c458af1e3172b992d550d74c330d4bb7683a3f91ad04811ac1e69afdea5b9a59` |
| `rows.mjs` | `c00f248c3c2593d132cc94a0f5b19853052cb03896e276cbc80316129166b6af` |
| `launch.ps1` | `e12fb9ea23fa6fde34b4df0e3048ac58b91ee045214fe6b383d4f79fc02bf6c0` |
