# Multi-window analyst workbench: architecture research

> Owner decision, 2026-11-13: #464 and #466 are closed as not planned for now.
> This research and its evidence are preserved as historical reference. Pending
> multi-window plans below are superseded by the
> [incremental delivery direction](../PRODUCT_DIRECTION.md#delivery-direction-2026-11-13).
> This decision does not claim that the proposed work was implemented or validated.

Research date: 2026-11-04. Status: conditional recommendation; not an approved architecture decision or implementation plan. Scope: local Windows CVMAnalytics, preserving React/Vite, Python financial services, SQLite, offline reads, and auditability. Sources below were consulted during this session; upstream `master`/`latest` documentation is not proof of the versions installed in the packaged application.

## Decision to make

Historical publication tracking (2026-11-05; superseded by the decision above): [initial desk research #465](https://github.com/joaosantossgp/analysis/issues/465)
is a documentation milestone under [goal #464](https://github.com/joaosantossgp/analysis/issues/464).
[Planning and validation #466](https://github.com/joaosantossgp/analysis/issues/466)
remained open for the unresolved choices and experiments below. Closing the
publication task does not mean research validation or implementation is complete.

For the clarified requirement, the most economical first candidate is the existing pywebview/WebView2 shell with explicit native-window management, plus a React docking layout concentrated in Home. This is an engineering-effort judgment grounded in existing code, **not a measured RAM, CPU, or latency victory**. Electron is the strongest alternative to investigate when browser-style tear-out/redock behavior is mandatory and pywebview integration proves costly. Tauri introduces a Rust host and Python sidecar without changing the Windows web engine; Qt offers native docking but entails a larger UI/integration decision.

The user corrected the priority during research: independent native windows with synchronized company/period context are primary; Home is a customized dockable/mosaic workspace where an analysis can also expand into an independent window. Thus all three patterns are relevant, with different ownership:

| Experience | Smallest useful architecture | Additional work |
| --- | --- | --- |
| Dockable panels plus detachable windows on multiple monitors | Docking layout in each native host, explicit panel transfer and shared context | Detach/redock semantics, cross-window drag, panel ownership, draft transfer |
| Independent native windows with synchronized context | Extend current pywebview child-window pattern | Window registry, linking channels, persistence, synchronization; no docking dependency required initially |
| Single-window mosaic and tabs | React docking or constrained splits in the current host | Panel context and layout persistence; no native popout requirement |

Use docking inside Home, and host-managed native windows for deep analysis. An explicit “Open in new window” action satisfies the expansion direction without relying on browser popout semantics. Seamless drag across operating-system windows is a separate interaction to validate if required; it must not be silently promised or treated as already delivered.

## Recommended experience for this application

Home remains the configurable research overview. Company analysis, financial statements, Excel Mapping, News and Indicators can open as independent native analysis windows where appropriate. A Home tile and its expanded view share analytical identity and data contracts; they need not share one DOM tree or mount an entire application shell inside a tile.

Proposed expansion behavior: retain the Home tile as a compact view and open or focus a detailed window with the same entity, period, indicator and report-basis context. This is a recommendation, not a settled rule: distinguish “open another view” from “move this panel,” and give editable work a single draft owner or explicit conflict handling. Closing the expanded view should not delete the Home configuration. Multiple views of one company must be possible when comparing different periods or statements; a registry keyed only by company, like the current mapping implementation, is insufficient for that general case.

Use explicit link groups rather than a globally selected company that changes every window. A linked group follows context changes; an unlinked or pinned window preserves a comparison. Identical contexts may reuse backend results, but each view retains its own display state and loading/error evidence.

Home already has a custom layout algorithm and browser-storage configuration in `apps/desktop-web/src/routes/HomePage.tsx:14–28`. `apps/desktop-web/src/components/home/WorkspaceRegistry.tsx:24` registers database status, watchlist, priorities, news and market-price widgets. These are useful starting points, not evidence of native expansion for every widget. Evaluate a docking library against these actual components before replacing the layout algorithm. The layout library handles Home arrangement; the desktop host handles windows; Base UI handles controls.

## Active repository evidence

Inspection was read-only except for this note. Existing unrelated changes were preserved. The canonical product direction explicitly prioritizes dense comparison, local ownership, fast local reads, and auditable Excel handoff: [PRODUCT_DIRECTION.md](../PRODUCT_DIRECTION.md), particularly lines 20–27 and 57–65. Source classes and missing/failure distinctions remain governed by [data-sources.md](../data-sources.md).

- `desktop/app.py:1240–1275` already maintains an Excel Mapping window registry keyed by CVM company code, protects it with an `RLock`, restores existing windows, creates native child windows, and removes closed windows from the registry. Child and main windows receive the same Python `bridge` object (`1257`, `1280`). This is a foundation for native windows, not evidence of a general docking workbench.
- `desktop/app.py:966` serves packaged assets from `127.0.0.1` with an ephemeral port. `desktop/app.py:1308` calls `webview.start(debug=debug_mode)` without explicitly configuring profile persistence. `requirements.txt:11` specifies `pywebview>=4.4`; the exact packaged version and backend behavior therefore need verification. `desktop/app.spec:70` identifies Windows EdgeChromium/WinForms packaging.
- `apps/desktop-web/src/lib/query.ts:8–14` creates a module-level QueryClient, with 60-second stale time, five-minute garbage collection, and focus refetch disabled. Independently bootstrapped webviews have separate JavaScript module instances; sharing the Python bridge is not sharing a React Query cache. A narrow storage listener for active coverage exists in `apps/desktop-web/src/components/shell/SubNav.tsx:83`; it is not evidence of a complete panel/event/cache synchronization protocol.
- `desktop/bridge_api/base.py:78–82` lazily initializes the read service without an explicit guard in that method. This is a concurrency-review item, not a demonstrated race failure. `desktop/bridge_api/energy.py:671,677` uses `webview.windows[0]` for file-dialog ownership, which needs review for independently active windows.
- Route-coupled company context appears in `apps/desktop-web/src/routes/CompanyDetailPage.tsx:60`, `CompanyStatementsPage.tsx:55`, and `CompanyModelMappingPage.tsx:81`. A single router URL cannot independently select several companies inside one layout. Panel instances need explicit entity/period/report-basis context while preserving existing route entry points.

## Native windows and browser popouts are different

Dockview supports tabs, split groups, floating groups, and browser popout groups; a floating group inside the page is not an operating-system window. Its popout API expects a host HTML page, normally `/popout.html`. A native shell must support the browser relationship required by the library, not merely be able to create another native window. [Dockview introduction](https://dockview.dev/docs/overview/introduction/), [popout groups](https://dockview.dev/docs/core/groups/popoutGroups/).

This is the decisive pywebview caveat. In the upstream EdgeChromium implementation inspected, `on_new_window_request` marks `NewWindowRequested` handled and passes the URI to a helper. That helper opens the system browser or navigates the existing view depending on configuration; it does not establish a new child WebView with the browser opener/DOM relationship. Therefore Dockview/FlexLayout browser popouts must not be promised as drop-in pywebview native windows. Verify the actual installed release before generalizing this source observation. [EdgeChromium implementation](https://raw.githubusercontent.com/r0x0r/pywebview/master/webview/platforms/edgechromium.py), [WebView2 helper, `_handle_new_window_request`](https://raw.githubusercontent.com/r0x0r/pywebview/master/webview/platforms/webview2core.py).

The lower-risk incremental approach is a host-created native window with its own React root. Transfer a serializable panel descriptor and user state; do not attempt to transfer live DOM or React objects. Each host can contain its own docking layout. Seamless native drag/redock still needs explicit integration and failure handling.

FlexLayout's browser popouts use React portals: code continues in the main window's JavaScript context while rendering into another document. Its documentation calls out document/window-specific listeners, third-party controls, background timer throttling, zoom, popup restoration, and placement restrictions. This may preserve React state elegantly in a compatible host, but is not equivalent to independently bootstrapped native roots. [FlexLayout popout documentation](https://raw.githubusercontent.com/caplin/FlexLayout/master/docs/popout-windows.md).

Electron explicitly maps `window.open` to a native BrowserWindow and supports same-origin child-window DOM access. Such child windows can share a process with the opener; do not assume every possible Electron window always creates a separate renderer. This is relevant evidence for evaluating browser-portal popouts, but chart, focus, drag, and shutdown behavior still need a real application trial. [Electron window opening](https://www.electronjs.org/docs/latest/api/window-open/).

## Options and costs

The effort judgments below are relative to this repository, not generic framework rankings.

| Option | Native windows / docking | Reuse and new responsibilities | Conditional assessment |
| --- | --- | --- | --- |
| Existing pywebview + WebView2 + React docking | Native windows already exist; docking is a React concern; native detach needs host integration | Reuse Python bridge, React screens, storage and packaging. Add panel context, window ownership, state transfer and lifecycle | First candidate for minimal migration and staged delivery |
| Electron + React docking + Python service | BrowserWindow and controlled browser popouts; docking still supplied by frontend | Reuse React and Python domain logic. Replace shell/bridge, manage Python lifecycle, IPC, installer and updater | Prefer evaluation if seamless browser-style popouts dominate and current host fails the gate |
| Tauri v2 + React docking + Python sidecar | Native windows through Tauri; Windows uses WebView2 | Reuse frontend and Python logic; add Rust host, capabilities, sidecar protocol, crash/restart and packaging contracts | Potential shell-platform choice; no automatic resource win over existing WebView2 |
| Qt/PySide6 native widgets | QDockWidget supports docked and independently positioned floating windows | Reuse Python core; native UI requires substantial frontend replacement. Keeping React via webviews changes bridge/packaging instead | Consider if native desktop interaction outweighs React reuse; not the first incremental step |

Tauri uses the operating system webview and supports bundled external binaries, including Python programs frozen into executables. Its sidecar packaging requires target-specific binaries. Retaining Python means its runtime, dependencies, memory, and operational lifecycle remain part of the product. A smaller Rust host binary is not a benchmark of the full application. [Tauri architecture](https://v2.tauri.app/concept/architecture/), [Windows webview](https://v2.tauri.app/reference/webview-versions/), [sidecars](https://v2.tauri.app/develop/sidecar/).

Qt's floating QDockWidget is an independent window associated with its QMainWindow and can be moved and resized. This provides native docking primitives, not evidence that current React components become native widgets without porting. [Qt for Python QDockWidget](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QDockWidget.html).

### Docking-library shortlist and licenses

Dockview is a reasonable first prototype candidate for docking, layout persistence, and explicit panel lifecycle APIs. Its current license matrix distinguishes MIT core from commercial Enterprise: core includes docking, popouts and save/restore, while spatial keyboard navigation and keyboard docking are Enterprise. Accessibility requirements must therefore be evaluated against the chosen edition, not inferred from “MIT.” [Dockview licensing](https://dockview.dev/docs/overview/licence/).

FlexLayout is MIT and offers a JSON layout model, tabsets, floating panels and popouts. Evaluate it alongside Dockview using the actual table/chart components and design tokens; documentation alone does not establish which integrates with less work. [FlexLayout repository and license](https://github.com/caplin/FlexLayout).

The repository's Base UI and Tailwind design rules still govern menus, dialogs, controls and visual tokens. Those controls and a docking-layout manager solve different responsibilities; a docking-library choice does not replace the existing design system.

pywebview uses BSD-3-Clause; Electron uses MIT; Tauri offers MIT/Apache-2.0. Qt for Python has LGPL/commercial terms and component-specific notices. These are upstream license identifications, not a legal conclusion about a distributable bundle; audit the selected versions and transitive/native components before release. [pywebview](https://github.com/r0x0r/pywebview), [Electron](https://github.com/electron/electron), [Tauri](https://github.com/tauri-apps/tauri), [Qt licenses](https://doc.qt.io/qtforpython-6/licenses.html).

## Shared state, persistence, and performance

Proposed design, not current functionality:

1. Keep one authoritative local service layer for financial reads, refresh jobs, exports and mutations. Windows send typed commands with a window identifier and explicit entity/period/source context. Do not start ingestion or a Python backend per panel. Preserve the accepted tiered storage contracts: SQLite metadata/dimensions/marts, managed analytical facts including hot SQLite and cold Parquet, summary reads by default, and detail bounded by entity and date. A multi-panel UI must not multiply full high-frequency scans. [ADR 0007, decision and implementation notes](../decisions/0007-local-analytical-storage.md), [ADR 0008, decision](../decisions/0008-database-alignment-before-app-development.md). Historical sizes in those ADRs are not current measurements.
2. Represent each panel with a stable ID, type, entity, period, consolidated/individual basis, units, source selection, link-group ID and view state. Separate this from native-window geometry and the docking-library layout JSON.
3. Make linking opt-in: two panels in one color group can follow a selected company or period while a pinned comparison stays unchanged. Use event IDs/revisions to prevent loops, reject stale results after a context switch, and invalidate affected query keys after writes or refreshes. Broadcast small invalidation/context events, not entire financial datasets.
4. Persist versioned workspaces and drafts under the application data root through the backend, with atomic writes and recovery. Browser storage should not be the sole durable workspace store, especially with an ephemeral local origin and unspecified profile settings. Financial source data remains in governed local storage; layout JSON is user configuration, not a new financial source.
5. Centralize service initialization and job ownership where concurrency tests demonstrate the need. Review SQLite connection/thread use, write serialization, cancellation and busy handling before enabling many simultaneously editable windows.

Start with a small host-authoritative event protocol through the existing bridge, rather than a new service platform or generalized event infrastructure. BroadcastChannel may be an optional fast path after verifying common origin/profile and delivery behavior; it must not become the sole durable authority or an assumption that all native hosts share browser storage.

WebView2 uses a browser-process group plus renderers and helpers. Instances with a compatible shared user-data folder/environment can share process resources; multiple folders create separate groups. This does not guarantee one renderer, one JavaScript heap, or one application cache. Validate the actual process tree and profile configuration rather than estimating memory by window count. [Microsoft process model](https://learn.microsoft.com/microsoft-edge/webview2/concepts/process-model), [user-data folders](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/user-data-folder).

Avoid fully mounting the existing application chrome and every route in every panel. Keep each panel narrowly scoped, paginate/virtualize large tables where measurement warrants it, reuse backend query results where safe, and stop hidden-panel work explicitly. Dockview's `onlyWhenVisible` changes DOM attachment; it does not destroy the panel instance or automatically stop queries, timers, or subscriptions. Chart resize behavior also needs testing when hidden dimensions become zero. [Dockview rendering](https://dockview.dev/docs/core/panels/rendering/).

## Security and offline behavior

Load trusted bundled UI in privileged windows. Validate message parameters and navigation origins, expose narrow commands, and keep arbitrary remote pages away from the financial/file bridge. Microsoft specifically recommends origin checks, input validation and avoiding generic host proxies. This is a design requirement, not a claim that an exploit was found in current code. [WebView2 security](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/security).

For Electron, preserve context isolation, sandboxing and restricted renderer privileges, and validate IPC senders. For Tauri, scope capabilities to the windows that need them; a Python service exposed outside capability-controlled commands needs its own access validation. [Electron security](https://www.electronjs.org/docs/latest/tutorial/security), [Tauri capabilities](https://v2.tauri.app/security/capabilities/).

Opening, linking or restoring a workspace must not trigger hidden financial-source refreshes. Downloaded data stays readable offline, and each panel must retain source, unit, period, timestamp, stale/partial/missing/error states. Workspace failures should recover to a safe layout without discarding drafts or inventing zero values. No application runtime was launched for this research; startup's existing update/metadata behavior was not exercised.

## Proposed validation sequence

These are future, bounded experiments, not authorization to install dependencies or implement them.

**First: establish the baseline.** Record packaged pywebview/WebView2/Python versions, renderer, profile configuration, machine/display specifications and dataset hash. Measure the existing main window plus its existing mapping windows before adding a library.

**Second: test the interaction contract.** Begin with read-only company and statement/chart panels, then add one editable mapping/draft panel to test draft ownership and transfer. Compare docking libraries inside the current host. For native windows, use explicit detach/redock first, then separately test cross-window dragging. Validate focus, shortcuts, clipboard, file-dialog ownership, modal parenting, draft preservation and correct company context. Do not remove the source panel until the target acknowledges a successful transfer.

**Third: test persistence and monitor topology.** Save and restore multiple workspaces; restart while offline; unplug/reconnect a monitor; change primary display, resolution and 100/125/150/200% scaling. Clamp restored windows to available work areas and provide “Bring all windows back.” Test closing child, parent and application with unsaved drafts, and recover from renderer/process failure.

**Fourth: measure equivalent workloads.** Use 1, 3 and 6 native windows and an eight-panel workload, including hidden panels and repeated company changes. Keep data, visible rows, calculations and refresh behavior identical. Record cold/warm startup, panel-open latency, context-switch p50/p95, stale-result correctness, idle/active CPU, UI stalls, total process-tree private bytes, working set, GPU memory if available, query counts and IPC payload volume. Do not sum shared working sets as if they were unique physical RAM. Repeat runs and report median, tail and variability; establish acceptance thresholds with the user before choosing a winner.

**Fifth: escalate only on evidence.** If current-host detach/drag behavior or measured responsiveness fails agreed requirements, test Electron with the same panels and Python service. Evaluate Tauri if its shell/capability/distribution model solves a demonstrated need. Consider Qt only when the value of native widgets justifies migration. A dev browser demo is not packaged Windows validation.

## Needs validation

- Whether expansion retains a Home preview or moves it, and whether seamless native cross-window dragging is required beyond explicit expansion. The primary independent-window model and Home docking/mosaic scope are confirmed.
- Exact installed/packaged pywebview behavior; upstream source was inspected, not the packaged executable. Local inspection found no `.venv/Scripts/python.exe`; no environment installation was attempted.
- Dockview/FlexLayout versions and React 19 compatibility, complete keyboard workflow and edition requirements.
- Native cross-window drag, redock and renderer crash behavior in the chosen shell.
- Backend initialization/thread safety, SQLite ownership and cross-window cache invalidation under load.
- Monitor/DPI placement, profile/process sharing, focus, file dialogs and draft-safe shutdown.
- Benchmarks and release-size measurements; none were run and no fastest/lowest-RAM claim is established.

Only this research note was added. No application code, dependency, runtime, database, issue, PR, commit, release or installation was changed by this research task.
