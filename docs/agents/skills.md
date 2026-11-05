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

Only those eleven skills are vendored. Superpowers, `grill-me`, `grilling` and
`domain-modeling` remain environment-level prerequisites; a fresh machine must
install them separately. The Vite UI contract remains in
`docs/skills/CVMANALYTICS_VITE_UI_SKILL.md`.

## Repository rules take precedence

Read `AGENTS.md` before invoking a skill. In particular:

- Use Superpowers for TDD and bug diagnosis.
- Use `ponytail-review` as the single pre-PR review gate, including when
  upstream `implement` requests `code-review`.
- Repository validation, source lineage and visible failure states override
  Ponytail simplification advice.
- Issue tracking and triage are configured in `docs/agents/issue-tracker.md`
  and `docs/agents/triage-labels.md`; do not run upstream setup automatically.

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

## Automatic maintenance

`.github/workflows/update-agent-skills.yml` checks every Monday at 12:17 UTC
(09:17 America/Sao_Paulo) and supports manual dispatch. It runs on the default
branch after integration. If an update PR is already open, it waits for review
instead of overwriting it. Otherwise, changed packages produce a new task issue
and a `chore/<issue>-agent-skill-updates` branch and PR. There is no auto-merge.
Skill-related PRs also run offline integrity checks and updater regression tests.

Before enabling PR publication, a repository administrator must create the
Actions secret `SKILL_UPDATE_TOKEN`: a fine-grained token restricted to this
repository with Contents, Issues and Pull requests read/write permissions.
Keep the token in GitHub Secrets, never in files. Organization policies must
also permit the token's access and GitHub Actions execution.

The dedicated token lets the resulting push/PR trigger normal CI. GitHub's
default `GITHUB_TOKEN` generally does not trigger subsequent workflows for its
own events. See [GitHub token documentation](https://docs.github.com/en/actions/concepts/security/github_token).
Without the secret, checks and downloads still run; when changes exist, the
workflow fails with setup instructions before creating an issue, branch or PR.

Activation requires merging the files into `main` and configuring that secret.
**Needs validation:** the first hosted scheduled/manual run, token permissions,
PR creation and downstream CI. Local tests do not establish hosted activation.
