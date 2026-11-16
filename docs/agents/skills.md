# Repository Agent Skills

## Installation and scope

The repository vendors eleven upstream skills in `.agents/skills/`. New clones
receive their complete directories; no package installation is required.
Codex discovers project skills there. `.gitignore` continues to ignore other
`.agents` content, and `.gitattributes` disables line-ending conversion for
vendored files so Windows clones preserve the upstream bytes and hashes.

| Upstream | Installed skills |
|---|---|
| [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | `ponytail`, `ponytail-review` |
| [mattpocock/skills](https://github.com/mattpocock/skills) | `grill-with-docs`, `to-spec`, `to-tickets`, `triage`, `wayfinder`, `implement`, `research`, `prototype`, `pr` |

`installation-manifest.json` records each source repository, source directory,
exact commit and SHA-256 of every installed file. The initial snapshots are
Matt Pocock `4ae2317ddb22b046e26455e4f9c9b3aaaf62212d` and Ponytail
`96608e078b2d5ea607c5c3b8b5a54d1c1fba6846`.
The upstream MIT license notices from these snapshots are retained in
`.agents/skills/licenses/`. Review upstream licensing when accepting updates;
these notices are maintained separately from the skill file manifests.

## Fresh-machine agent setup

Only those eleven skills are bundled and pinned. The Vite UI contract is a local
required document at `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md`, not an external
plugin dependency. Verify the vendored set with the offline command below.

Superpowers, `grill-me`, `grilling` and `domain-modeling` are external skills.
Their availability and versions depend on the host; cloning this repository does
not install them. Check the host skill catalog before planning a task. When using
an external skill, record its name and installed version or source in the working
plan so another machine can reproduce the chosen process. Do not install or update
global plugins silently, and do not invoke a skill that is absent.

The repository workflow remains executable without external plugins:

| Need | Required equivalent when the external skill is unavailable |
|---|---|
| Design clarification | Inspect the owning workflow and ask only scope/correctness questions; record the decision in the issue. |
| Implementation plan | Record files, contracts, acceptance and checks in the issue; local working notes may live in `docs/superpowers/`. |
| Bug diagnosis | Reproduce, trace the failing layer and identify the cause before editing. |
| TDD | For non-trivial behavior, add a regression, observe failure, implement and run the relevant suite. |
| Isolated work | Use the host worktree tool or Git; follow AGENTS.md branch/issue rules. |
| Verification and delivery | Run AGENTS.md checks, use vendored `ponytail-review`, then PR -> CI -> merge. |

An explicitly requested missing skill is not silently substituted: report its
absence and follow the host's installation/permission rules. Humans use the same
acceptance criteria and commands; they do not need an agent plugin to contribute.

## Repository rules take precedence

Read `AGENTS.md` before invoking a skill. Its workflow, validation and reporting
rules override duplicate skill templates. In particular:

- Prefer available Superpowers skills for TDD and bug diagnosis; otherwise use
  the equivalent process above.
- Use `ponytail-review` as the single pre-PR review gate, including when
  upstream `implement` requests `code-review`.
- Repository validation, source lineage and visible failure states override
  Ponytail simplification advice.
- Issue tracking and triage are configured in `docs/agents/issue-tracker.md`
  and `docs/agents/triage-labels.md`; do not run upstream setup automatically.
- The [PR template](../../.github/PULL_REQUEST_TEMPLATE.md) documentation-impact
  contract also applies when using the vendored `pr` skill: include a
  **Documentation impact** section naming the updated owner docs or explaining
  why no update is needed. Use the
  [Documentation Gate](../PRODUCT_DEVELOPMENT_CHECKLIST.md#12-documentation-gate)
  to select those owners.

Keep upstream files byte-exact. Record project adaptations in `AGENTS.md` or
this document, not inside downloaded skills. Installing these files does not
install Ponytail plugin hooks or execute downloaded scripts.

## Verification and manual updates

From the repository root:

```powershell
# Offline verification: exact file inventory and SHA-256 hashes.
python scripts/governance/update_agent_skills.py --verify

# Regression tests without external requests or application dependencies.
python -m unittest scripts.governance.test_update_agent_skills

# Fetch current upstream main snapshots for the existing allowlist.
python scripts/governance/update_agent_skills.py
```

The updater refuses locally changed files. It downloads and validates every
selected package before writing, checks downloaded Git blob hashes, rejects
unsafe paths and symlinks, and retains the old snapshot if fetching or
validation fails. An upstream file that replaces an installed directory is
rejected before any package is changed; review that layout change manually.
A filesystem failure during installation may leave partial
writes: restore `.agents/skills/` from the last reviewed commit and verify.
Unknown upstream skills are never added automatically. An unchanged package
retains its existing pin even if the upstream repository has unrelated commits.

Review changes before delivery, run verification again, and follow the normal
issue/PR/CI/merge workflow. To roll back a published update, revert its PR and
run the offline verifier. No application tests are replaced by this verifier.

## Manual maintenance policy

Update vendored skills only when explicitly requested. Run the local update
command above, review the upstream instruction and license changes, verify the
result, and deliver through the normal issue/PR/CI/merge workflow. The harness
loading these repository files does not itself refresh their pinned contents.

`.github/workflows/update-agent-skills.yml` only runs offline integrity checks
and updater regression tests on skill-related pull requests or manual dispatch.
It does not fetch upstream updates or create issues, branches or PRs. There is
no scheduled update job and no dedicated publication token to configure.
