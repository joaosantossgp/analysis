# 0011: Build-once publications and update channels

Status: Accepted (2026-11-26). Being implemented under goal #623: shipping
classes (#625), the decision module (#628) and the build-once publication
workflow (#629) are in place and [`../release-process.md`](../release-process.md)
describes the operating flow; promotion, installer, candidate test command,
retention and the update channel are still to land.

## Context

The app is meant to be distributed to other people and to update itself. The
last release is `v0.29.2` (2026-07-09) and the last pre-release is
`v0.30.0-rc.1` (2026-07-16); 258 commits on `main` are unpublished. The
three-phase gate (candidate -> attest -> publish) was added after that and has
never published anything. The in-app updater reads only GitHub's "latest"
release, so installed apps never see pre-releases. The owner tests packaged
builds by downloading and extracting a ZIP by hand. There is no stated rule for
when a pre-release or a release happens.

Publishing terms used below are defined in [`../../GLOSSARY.md`](../../GLOSSARY.md).

## Decision

- **One number sequence.** Versions are plain `MAJOR.MINOR.PATCH`, with no
  `-rc` suffix. The first publication under this scheme is `0.30.0`. `pre` and
  `hotfix` work raise PATCH; a large `release` raises MINOR.
- **Every publication is a cumulative build of `main`.** It is published either
  as a pre-release or directly as a release.
- **Build once, then promote.** A release made from earlier pre-releases is a
  promotion of an existing pre-release: same file, same number, no rebuild.
- **Update channels.** The installed app offers "releases only" (default) or
  "pre-releases and releases", with a notice that pre-releases bring features
  sooner and may be less stable. Everything in a pre-release reaches the next
  release.
- **Shipping class per issue**, set at triage and changeable by the owner:

  | Class | Applies to | On merge |
  |---|---|---|
  | `none` | docs, CI, tests, dev tooling, repository work | nothing is published |
  | `pre` | small or medium functionality or fixes, visible or not | a pre-release |
  | `release` | a large or medium-large implementation | a direct release when its last part merges |
  | `hotfix` | a bug that breaks the current release | an immediate release |

- **Approval.** A `pre` publication outside the risk areas publishes on green
  CI with no approval. A `pre` publication touching a risk area, and every
  release, waits for the owner to test the candidate and approve, either in the
  agent chat for that specific version or in the GitHub `release-publication`
  environment. A script downloads, extracts and opens the candidate; the owner
  does not handle the ZIP.
- **A pending test holds publication, not development.** Because builds are
  cumulative, later publications wait too, and the owner tests the latest
  `main` once.
- **Time-based promotion.** When the oldest unpromoted pre-release reaches 30
  days, the agent proposes promoting the newest pre-release that is at least 20
  days old. Younger pre-releases wait for the next cycle. If that pre-release
  has a blocking bug fixed in a newer one, the newer one is promoted instead.
  The owner can also ask for a promotion at any time.
- **Unfinished work stays unreachable.** Parts of a `release`-class
  implementation merge into `main` incrementally and travel inside later
  pre-releases; they must have no route, entry point or control until the last
  part lands. Reviews check this explicitly.
- **First install uses an installer** (`Setup.exe`, per-user, no admin). The
  ZIP remains the updater's package. No code-signing certificate for now.

## Considered options

- Keep the three-phase gate for every publication: rejected because it needs
  three manual dispatches and attestations per version and produced no
  publication in four months.
- A pre-release on every merge with no approval: rejected because other people
  will run pre-releases, and a risk-area change must not reach them untested.
- `-rc.N` or `git describe` version names for pre-releases: rejected by the
  owner as unreadable.
- Batching pre-releases by period: rejected because it delays small features;
  time governs promotion to release instead.
- Holding all pre-releases while a large implementation is open: rejected
  because it blocks small deliveries for weeks.

## Consequences

- `docs/release-process.md`, `docs/build-release.md` and
  `.github/workflows/release-desktop.yml` must be rewritten to this model; the
  attestation records and the #440 approval step are replaced by the approval
  rule above.
- The updater must list releases instead of reading only "latest", honor the
  update channel, and keep accepting already-published `-rc.N` tags so existing
  installs can still compare versions. Asset names stay unchanged so installs
  on `v0.29.2` can update.
- An installed app on the pre-release channel that switches to "releases only"
  stays on its version until a release passes it.
- Without code signing, Windows SmartScreen warns on first run of the
  installer.
- Triage must assign a shipping class to every issue, and the triage labels doc
  must define the four labels.
- Old pre-releases need a retention rule so GitHub Releases does not accumulate
  hundreds of entries. Needs validation: how many to keep.
