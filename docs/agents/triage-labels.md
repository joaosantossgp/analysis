# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the "Label in our tracker" column to match whatever vocabulary you actually use.

## Shipping class

Every task and bug carries exactly one shipping class label, which says what its
merge publishes ([ADR 0011](../decisions/0011-build-once-publications-and-update-channels.md),
`GLOSSARY.md` "Publishing"). Goals get no class.

| Label           | Applies to                                                  | On merge                                   |
| --------------- | ----------------------------------------------------------- | ------------------------------------------ |
| `ships:none`    | Docs, CI, tests, dev tooling, repository work               | Nothing is published                       |
| `ships:pre`     | Small or medium functionality or fixes, visible or not      | A pre-release                              |
| `ships:release` | The ticket that makes a large implementation reachable      | A release (direct, when this part merges)  |
| `ships:hotfix`  | A bug that breaks the current release                       | An immediate release                       |

- **Who sets it:** `/triage` applies the label when it moves an issue out of
  `needs-triage`. The task and bug templates ask the reporter for a suggestion;
  triage decides. The owner can change the label at any time before the PR
  merges.
- **Large implementations:** only the ticket that makes the work reachable in
  the app carries `ships:release`. Earlier parts carry `ships:none` and must stay
  unreachable in the app until that ticket lands; the PR template asks the
  author to confirm this and `/ponytail-review` checks it.
- **PR check:** `.github/workflows/pr-issue-guardrails.yml` resolves a PR's class
  as the highest label among the issues it closes
  (`hotfix` > `release` > `pre` > `none`) and fails when no closed issue has
  one. Goals referenced with `Refs #n` are not counted. After relabelling an
  issue, edit or push to the PR to re-run the check.
