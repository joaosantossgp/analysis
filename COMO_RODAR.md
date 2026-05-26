# Como Rodar - CVM Analytics

Guia pratico para baixar o app desktop e, quando necessario, subir o app local oficial e as superficies de desenvolvimento.

Fluxo principal atual:

`download da release -> extrair ZIP -> abrir CVM Analytics`

Fluxo de desenvolvimento:

`runtime_doctor.py -> setup_db.py -> setup_companies_table.py -> python -m desktop.app --dev -> desktop/build_desktop.ps1 -> dist/CVMAnalytics/CVMAnalytics.exe`

---

## 1. Baixar o app desktop

Para uso final no Windows, baixe a ultima release:

```text
https://github.com/joaosantossgp/analisys/releases/latest/download/CVMAnalytics-windows.zip
```

Depois:

1. Extraia o ZIP em uma pasta fixa.
2. Abra o executavel do CVM Analytics.
3. Atualize a base local pelo proprio app.

A pagina publica de download vive em `landing/` e e publicada via GitHub Pages. O deploy Vercel foi aposentado.

---

## 2. Preparar o ambiente de desenvolvimento

Entre na pasta do projeto:

```powershell
cd C:\caminho\para\cvm_repots_capture
```

Crie e ative a `.venv` se necessario:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale as dependencias Python:

```powershell
pip install -r requirements.txt
pip install -r apps/api/requirements-dev.txt
```

Se for trabalhar na interface desktop:

```powershell
cd apps/desktop-web
npm install
cd ..\..
```

Se for trabalhar em uma task versionada, prefira criar uma worktree antes de
editar arquivos:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/worktree_create.ps1 -Issue 27 -Slug exemplo-task -Lane ops-quality
```

Ao concluir a task, prefira finalizar a PR com o helper abaixo para esperar
checks, mergear e confirmar o fechamento:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/pr_complete.ps1 -Pr 28
```

---

## 3. Diagnosticar o runtime

Bootstrap minimo:

```powershell
python scripts/runtime_doctor.py --require-canonical
```

Diagnostico completo:

```powershell
python scripts/runtime_doctor.py --require-db --table financial_reports --table companies --require-canonical
python scripts/canonicalize_data_layout.py
python scripts/db_portability_smoke.py --write-check
```

Validacao de PostgreSQL sem exportar variavel:

```powershell
python scripts/runtime_doctor.py --database-url postgresql://user:pass@host:5432/db --require-db --table financial_reports --table companies
python scripts/db_portability_smoke.py --database-url postgresql://user:pass@host:5432/db --write-check
```

---

## 4. Inicializar o banco

Em maquina nova ou depois de migracao:

```powershell
python scripts/setup_db.py
python scripts/setup_companies_table.py
```

Opcional:

```powershell
python scripts/expand_tickers.py --dry-run
```

---

## 5. Atualizar dados financeiros

### Opcao A - App desktop oficial

```powershell
python -m desktop.app --dev
```

Para validar o modo distribuivel:

```powershell
.\desktop\build_desktop.ps1
.\dist\CVMAnalytics\CVMAnalytics.exe
```

### Opcao B - CLI pontual

```powershell
python main.py --companies PETROBRAS --start_year 2021 --end_year 2025 --type consolidated --skip_complete
```

### Opcao C - Lote headless

```powershell
python scripts/batch_completo.py --dry-run
python scripts/atualizar_todos.py --anos 2024 2025
```

Smoke seguro do fluxo API + bridge da pagina **Atualizar base** (default
`mode=missing`, `limit=1`; live so com `--confirm-live`):

```powershell
python scripts/update_base_smoke.py --dry-run --mode missing --limit 1
```

Detalhes: `docs/governance/on-demand-release-evidence.md` (secao Smoke Atualizar Base).

Os logs ficam em `output/logs/`.

---

## 6. Subir a API da V2

```powershell
uvicorn apps.api.app.main:app --reload
```

Abrir:
- Swagger: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`

Endpoints principais:
- `GET /health`
- `GET /companies`
- `GET /companies/filters`
- `GET /companies/{cd_cvm}`
- `GET /companies/{cd_cvm}/years`
- `GET /companies/{cd_cvm}/statements`
- `GET /companies/{cd_cvm}/kpis`
- `GET /refresh-status`
- `GET /base-health`

Exemplos:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/companies?search=petro&page=1&page_size=20"
Invoke-RestMethod http://127.0.0.1:8000/companies/filters
```

---

## 7. Subir a UI desktop Vite

A UI ativa fica em `apps/desktop-web`. Ela e uma SPA Vite carregada pelo
desktop pywebview. O app antigo em Next.js (`apps/web`) foi removido da arvore
ativa.

Em outro terminal:

```powershell
cd apps/desktop-web
npm run dev
```

Abrir:
- preview Vite: `http://127.0.0.1:5173`

Rotas principais:
- `/`
- `/empresas`
- `/empresas/[cd_cvm]`
- `/setores`
- `/atualizar-base`
- `/status`

Observacoes:
- no app real, os dados passam pelo bridge `window.pywebview.api`
- componentes React devem chamar as facades em `apps/desktop-web/src/lib/api/`
- para testar com bridge real, prefira `python -m desktop.app --dev`

---

## 8. Validar tudo

Suite principal:

```powershell
pytest tests/ -q
pytest apps/api/tests -q
```

Desktop UI:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

Validacoes de workbook/exportacao (QA manual; rode somente apos gerar o
XLSX via `main.py` ou pelo export do desktop). Nao sao requisitos de
setup nem rodam em CI.

QA estrutural reutilizavel (rode contra qualquer workbook gerado, ajuste
`--xlsx` conforme necessario):

```powershell
python scripts/quick_verify.py --xlsx output/reports/PETROBRAS_financials.xlsx
python scripts/verify_consolidation.py --xlsx output/reports/PETROBRAS_financials.xlsx
python scripts/verify_line_id_base.py --xlsx output/reports/PETROBRAS_financials.xlsx
```

Verificacao historica de bug-fixes (campanha antiga de 4 bugs: cobertura
de anos, replicacao BPP, totais BPA, recorte consolidado). Mantida para
regressao manual contra o export da Petrobras; nao e parte do fluxo
normal:

```powershell
python scripts/final_verification.py --xlsx output/reports/PETROBRAS_financials.xlsx
```

Todos compartilham o helper `scripts/workbook_paths.py` (resolucao de
caminho XLSX padrao/legado).

---

## 9. Desktop pywebview

App nativo com janela pywebview + UI Vite. O bridge Python responde
diretamente, sem precisar do servidor FastAPI para leitura.

### Modo dev (recomendado para desenvolvimento)

O comando abaixo inicia ou reutiliza o Vite dev server em `127.0.0.1:5173`
e abre a janela pywebview. FastAPI nao e necessario para a leitura local,
porque o bridge Python responde direto para a UI.

```powershell
python -m desktop.app --dev
```

### Modo standalone (sem npm run dev)

Gere o executavel; o app empacotado serve a build Vite estatica por HTTP local:

```powershell
.\desktop\build_desktop.ps1
.\dist\CVMAnalytics\CVMAnalytics.exe
```

> O bridge Python responde diretamente no modo standalone; FastAPI nao e necessario
> para leitura de dados.

### Flags

| Flag | Efeito |
|---|---|
| `--dev` | Inicia ou reutiliza `http://127.0.0.1:5173` (Vite dev server) |
| `--debug` | Abre DevTools no modo ativo |
| (nenhuma) | Serve `apps/desktop-web/dist` ou `_internal/desktop-web` e carrega o app |

### Teste de sanidade (com `--debug`)

Abra o console do DevTools e execute:

```javascript
await window.pywebview.api.ping()
// => {pong: true, ts: 1234567890.0}

await window.pywebview.api.get_companies({page: 1, page_size: 5})
// => {items: [...], pagination: {...}}
```

---

## Problemas comuns

| O que aconteceu | O que fazer |
|---|---|
| `ModuleNotFoundError` ao abrir o desktop | Use `python -m desktop.app --dev` para rodar o app. |
| `python` nao reconhecido | Instale o Python e coloque no `PATH`. |
| `runtime_doctor.py` falha com `venv-broken` | Recrie a `.venv` com `python -m venv .venv`. |
| App desktop abre sem empresas | Rode `setup_db.py`, `setup_companies_table.py` e atualize dados. |
| API responde `503` | Valide o banco, tabelas obrigatorias e o `runtime_doctor.py`. |
| Erro de permissao no PowerShell | Rode `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| UI Vite nao abriu no desktop | Rode `npm --prefix apps/desktop-web run build` ou use `python -m desktop.app --dev`. |
