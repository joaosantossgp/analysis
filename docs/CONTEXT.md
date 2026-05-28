# CONTEXT.md - CVM Reports Capture

> Referencia tecnica: regras de negocio, pipeline, arquitetura e troubleshooting.
> Para regras operacionais e convencoes de agentes, veja `AGENTS.md` na raiz.

---

## 1. O que e o projeto

Extrai demonstracoes financeiras historicas de companhias listadas na CVM, organiza em SQLite local (PostgreSQL opcional) e expoe os dados via app desktop pywebview (Vite UI estatica + bridge Python) e API FastAPI read-only para hospedagem/dev/local. O foco e produzir output confiavel, legivel e verificavel sem misturar periodos, versoes ou linhas conflitantes.

**Objetivo final:** pipeline unico que recebe empresa + ano inicial/final, persiste demonstracoes e metadados em banco e disponibiliza consulta/exportacao via app desktop, API HTTP e Excel auditavel.

**Fonte de dados:** CVM publica - `https://dados.cvm.gov.br` (DFP anual + ITR trimestral).

---

## 2. Escopo tecnico atual

**Prioridade 1 (concluida):** integridade contabil e periodizacao correta - fechar Ativo/Passivo Total, evitar carimbar anual em trimestre, tratar janela de anos.

**Prioridade 2 (concluida):** chave estavel `LINE_ID_BASE`, base wide, `DS_CONTA_norm`, filtro `ORDEM_EXERC='ULTIMO'`, QA por conflitos, exportacao limpa do Excel.

**Prioridade 3 (concluida):** padronizacao por dicionario de contas (`STANDARD_NAME`), aba `PADRONIZACAO` no Excel.

**Prioridades 4-8 (concluidas):** expansao em massa (449 empresas), vetorizacao + WAL + paralelismo, API FastAPI, migracao do app desktop para pywebview com Vite estatico empacotado, testes automatizados. A antiga UI Next.js foi removida da arvore ativa.

---

## 3. Regras de negocio essenciais

- Output gera abas **BPA**, **BPP**, **DRE** e **DFC**.
- Linhas identificadas por `LINE_ID_BASE` estavel - sempre usa `CD_CONTA` quando disponivel; chave sintetica deterministica quando nao.
- `DS_CONTA_norm` obrigatorio em todas as abas: lower, remocao de acentos, trim, colapso de espacos, remocao de NBSP.
- Output nao deve usar sufixos artificiais como `#1`, `#2`.

### Regras DRE e DFC

- DRE e DFC mantem colunas trimestrais e anuais (`1Q`, `2Q`, `3Q`, `4Q`, `YYYY`).
- DFC nao fica cumulativa: conversao YTD -> standalone feita internamente.
  - `Q1 = YTD_1Q`
  - `Q2 = YTD_2Q - YTD_1Q`
  - `Q3 = YTD_3Q - YTD_2Q`
  - `Q4 = ANUAL - YTD_3Q`
  - `YYYY = ANUAL`
- Trimestre faltante: deixar `NaN` e registrar no QA; nao inventar valores.
- `4Q` depende da presenca do anual `YYYY`; trimestre isolado nao gera `4Q`
  confiavel.

### QA e criterios de aceite

Validacoes obrigatorias antes de exportar Excel:
- `LINE_ID_BASE` unico por aba
- `DS_CONTA_norm` sem nulos
- ausencia de `"#"` nos IDs finais
- fechamento BPA e BPP (Ativo Total = Passivo Total)
- DFC: `Q1 + Q2 + Q3 + Q4 = YYYY` quando todos os periodos existirem

Abas **QA_LOG** e **QA_Errors** sao obrigatorias para rastreabilidade.

---

## 4. Pipeline e data flow

### Ciclo completo (download -> banco -> consulta)

**1. Trigger**
- CLI: `python main.py --companies ... --start_year ... --end_year ...`
- Desktop app (`desktop/app.py`): invoca o scraper via bridge para empresas/range selecionados na UI
- Scripts em lote: `scripts/batch_completo.py`, `scripts/atualizar_todos.py`

**2. Download e extracao**
- `src/scraper.py` baixa ZIPs da CVM para `data/input/raw`
- CSVs (BPA/BPP/DRE/DFC/DVA/DMPL) sao extraidos para `data/input/processed`

**3. Transform e normalizacao**
- filtra por `CD_CVM`, normaliza unidades financeiras
- deriva labels de periodo, monta tabelas por demonstracao
- gera `LINE_ID_BASE`, aplica padronizacao e logs de QA

**4. Persistencia**
- `src/database.py` escreve linhas long-form em `financial_reports` e eventos de QA em `qa_logs`
- metadados de empresa sao atualizados em `companies`
- status de refresh persistido em `company_refresh_status`
- exportacao Excel disponivel em `output/reports/`

**5. Consulta**
- `src/read_service.py` e a fonte de verdade da camada de leitura
- `apps/api` (FastAPI) e o adaptador HTTP fino sobre `read_service`
- App desktop usa o Vite SPA em `apps/desktop-web` e o bridge Python direto via `desktop/bridge.py`, evitando o salto HTTP em runtime local

### Modelo de cobertura

- **Universo:** empresas ativas da CVM master
- **Celula coberta:** empresa-ano com pacote completo (`BPA + BPP + DRE + DFC`)
- **Ano fechado:** so conta como coberto quando o pacote completo existir no
  periodo anual `YYYY`; `1Q/2Q/3Q` sem anual nao contam como cobertura anual
- **Sinal hibrido:** `financial_reports` + arquivos raw/processados + cache local

---

## 5. Arquitetura de pastas

```text
cvm_repots_capture/
|-- src/                        # Pipeline de extracao e processamento
|   |-- scraper.py              # CVMScraper
|   |-- database.py             # CVMDatabase
|   |-- db.py                   # get_engine() SQLite/PostgreSQL
|   |-- standardizer.py         # AccountStandardizer
|   |-- query_layer.py          # Camada de leitura
|   |-- read_service.py         # Servico de leitura canonico (consumido pelo apps/api e bridge)
|   |-- refresh_service.py      # Servico de refresh headless
|   |-- kpi_engine.py           # KPIs financeiros
|   |-- excel_exporter.py       # Exportacao Excel
|   |-- statement_summary.py    # Resumos de demonstracoes
|   |-- ticker_map.py           # Mapa CVM -> ticker
|   `-- utils.py                # Helpers compartilhados
|-- desktop/                    # App desktop oficial (pywebview + Vite estatico)
|   |-- app.py                  # Entry point pywebview
|   |-- bridge.py               # Bridge Python expondo read/refresh para a UI
|   |-- services.py             # Logica de negocio compartilhada
|   |-- build_desktop.ps1       # Script de build do .exe via PyInstaller
|   `-- updater.py              # Auto-updater do desktop
|-- apps/
|   |-- api/                    # FastAPI read-only (adaptador HTTP hospedado/dev)
|   `-- desktop-web/            # Vite SPA empacotada no desktop
|-- scripts/                    # Setup, batches, dicionario canonico e validacoes
|-- archive/                    # Scripts e governanca antigos
|-- tests/                      # Suite pytest
|-- data/
|   |-- db/cvm_financials.db    # SQLite local
|   |-- cache/                  # Caches auxiliares
|   `-- metadata/               # Metadados de empresas e tickers
|-- docs/
|   |-- CONTEXT.md              # Este arquivo
|   |-- decisions/              # ADRs
|   |-- governance/             # Autonomous-mode contract
|   |-- reference/              # Docs de referencia ativos
|   `-- vendor/                 # Manuais CVM (PDF/XLS) para leitura humana
|-- main.py                     # Entrypoint CLI
|-- AGENTS.md                   # Regras operacionais para agentes
|-- README.md                   # Overview do projeto
`-- COMO_RODAR.md               # Tutorial passo a passo
```

---

## 6. Stack e convencoes de codigo

**Stack:**
- Python: 3.11+, pandas, polars, sqlalchemy, requests, yfinance, pywebview, PyInstaller
- Desktop UI: Vite, React, TypeScript, Tailwind v4
- API hospedada/dev: FastAPI (read-only)
- DB: SQLite local + PostgreSQL opcional via `DATABASE_URL`

**Convencoes:**
- `snake_case` para variaveis e nomes de arquivos
- OO no motor principal (`CVMScraper`)
- bloco `USER CONFIGURATION` no topo de cada script executavel
- `LINE_ID_BASE` como identificador canonico

---

## 7. Estado atual

- Banco local SQLite com suporte opcional a PostgreSQL via `DATABASE_URL`
- App desktop oficial: `desktop/app.py` (pywebview + Vite estatico em `dist/CVMAnalytics/CVMAnalytics.exe`)
- API FastAPI read-only em `apps/api` para dev/local HTTP (self-host opcional); nao e empacotada no desktop. Nao assuma hospedagem Vercel/Railway: o produto canonico e o `CVMAnalytics.exe`.
- UI ativa em `apps/desktop-web`; a antiga UI Next.js em `apps/web` foi removida
- Automacao e batches via `scripts/batch_completo.py` e `scripts/atualizar_todos.py`

**Proximas prioridades:**
- ampliacao de cobertura/contas para outros setores
- melhorias na auditabilidade dos KPIs financeiros
- documentacao operacional e exportacoes auxiliares

---

## 8. Bootstrap rapido (Windows)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_windows.ps1
```

Flags: `-ForceRecreateVenv`, `-SkipSmoke`.

Fluxo pos-bootstrap recomendado:
```powershell
.\.venv\Scripts\Activate.ps1
python scripts/setup_db.py
python scripts/setup_companies_table.py
python -m desktop.app --dev
```

Fluxo alternativo via CLI:
```powershell
.\.venv\Scripts\Activate.ps1
python main.py --companies PETROBRAS --start_year 2021 --end_year 2025 --type consolidated
uvicorn apps.api.app.main:app --reload
```

---

## 9. Troubleshooting

| Sintoma | Diagnostico |
|---------|-------------|
| Sem dados no app | Verificar se `financial_reports` tem linhas e se a empresa/anos selecionados foram processados |
| Empresa ausente | Verificar se o `CD_CVM` foi processado com sucesso |
| SQL error no updater | Inspecionar logs em `output/logs/refresh_runs.jsonl` e confirmar que o SQLite nao esta bloqueado |
| Lista repete as mesmas empresas | Verificar se `last_success_at` esta sendo atualizado em `company_refresh_status` |
| ETA nao aparece | Comportamento esperado quando ainda ha poucas amostras de throughput |
| Numeros de cobertura desatualizados | Forcar refresh do ranking e checar o cache local |
| Widgets de mercado vazios | Verificar disponibilidade do yfinance e mapeamento de ticker |
| Cockpit retorna vazio | Checar `apps/api/app/routes/` e a cobertura real da empresa/anos selecionados |

---

## 10. Decisoes Tecnicas Nao-Obvias

Decisões de implementação que não são óbvias da leitura do código e que já causaram bugs no passado:

| Decisao | Razao |
|---------|-------|
| `int(year)` antes de param SQLite | numpy int64 falha silenciosamente |
| yfinance `dividendYield` ja em % | nao multiplicar por 100 |
| SQLAlchemy IN clause: `bindparam("x", expanding=True)` | listas como params SQL |
| `_upsert_company_metadata`: INSERT OR IGNORE + UPDATE | preserva CNPJ/ticker preenchidos por `setup_companies_table` |
| `fillna("")` antes de `pivot_table` | evita perda silenciosa de linhas com `STANDARD_NAME` nulo |
| `apps/api` consome `src/read_service.py` | evita reimplementar SQL e KPI logic no adaptador HTTP |
