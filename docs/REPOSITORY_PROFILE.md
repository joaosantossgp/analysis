# Repository Profile

GitHub "About" values for `joaosantossgp/analysis`, verified through the repository
API on 2026-11-16. This is the maintenance reference for profile changes.

## Description

Local-first Windows desktop financial data tool for Brazilian public companies, built with Python, SQLite, pywebview, and Vite.

## Website / Homepage

[CVMAnalytics landing page](https://joaosantossgp.github.io/analysis/), sourced from
`apps/landing/` and deployed by
[deploy-landing.yml](../.github/workflows/deploy-landing.yml#L39).
The product runtime is the packaged Windows desktop executable.

## Topics

```text
brazilian-market
cvm
data-pipeline
desktop-app
equity-research
financial-data
python
pywebview
sqlite
vite
windows
```

## Releases

The [latest stable release](https://github.com/joaosantossgp/analysis/releases/latest)
provides the stable asset alias
[CVMAnalytics-windows.zip](https://github.com/joaosantossgp/analysis/releases/latest/download/CVMAnalytics-windows.zip)
and its checksum, alongside versioned ZIP/checksum assets. Repository access is
required while the repository is private; these are not anonymous public downloads.

The ZIP root contains `CVMAnalytics.exe` and `_internal/`. The authoritative layout,
versioning and updater contract is [build-release.md](build-release.md).

## Update commands

Run only for an intended profile update; these commands do not deploy the landing page.

```bash
gh repo edit joaosantossgp/analysis \
  --description "Local-first Windows desktop financial data tool for Brazilian public companies, built with Python, SQLite, pywebview, and Vite." \
  --homepage "https://joaosantossgp.github.io/analysis/" \
  --add-topic brazilian-market --add-topic cvm --add-topic data-pipeline \
  --add-topic desktop-app --add-topic equity-research --add-topic financial-data \
  --add-topic python --add-topic pywebview --add-topic sqlite \
  --add-topic vite --add-topic windows
```
