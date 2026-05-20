# Handoff — Continue GICS migration from Fase 3

Cole esta mensagem inteira no início da próxima sessão.

---

Você está retomando uma migração GICS em andamento neste projeto. Antes de qualquer coisa, leia:

1. `C:\Users\jadaojoao\.claude\plans\tender-pondering-russell.md` — o plano completo da migração em 4 fases.
2. `data/reports/ui-audit-20260516/REPORT.md` — auditoria visual que originou as Fases 1-2 (foco em P0/P1).
3. Os dois últimos commits do branch `main`:
   - `18fe1a8` — Fase 1 (GICS-strict display + P0 a11y).
   - `bd7e510` — Fase 2 (link "Ver setor" via GICS slug + tests).

## Regras de ouro deste projeto

1. **O produto é o .exe**, não o web preview. O .exe roda Next bundled com pywebview, e os dados vêm de `desktop/bridge.py` → `src/read_service.py` direto. **NÃO há servidor HTTP em produção.**
2. **`apps/api/` está fora de escopo**. É uma vitrine paralela com bugs preexistentes (drop dos campos `gics_sector` no payload). Não tente "consertar" o `next dev` web preview tocando em `apps/api/`. Se quebrar, deixa quebrado.
3. Mudanças válidas são em: `apps/web/` (UI bundled no .exe), `src/` (camada compartilhada), `desktop/bridge.py`. Memória do projeto reafirma isso.
4. Verificação confiável: chamar `src/read_service.py` direto em Python (igual o bridge faz). NÃO confie no `next dev` HTTP API para validar GICS — ele tem bug separado que mostra "Não classificado" mesmo quando o DB tem dado.

## Estado atual confirmado

- **DB tem GICS em 100% das empresas** (671/671). VALE=Materials, PETROBRAS=Energy, AMBEV=Consumer Staples, etc.
- **`read_service.list_companies(sector_slug="energy")` retorna 19 empresas**; `sector_slug="energia-eletrica"` retorna 0 (legacy → corte limpo, sem precisar de whitelist explícita).
- **`read_service.get_sector_detail(sector_slug="energia-eletrica")` retorna None** → `notFound()` natural no Next.
- **Constants frontend já têm `GICS_SECTORS`, `GICS_SECTOR_SLUGS`, `GICS_SECTOR_BY_SLUG`, `GICS_SLUG_SET`, `UNCLASSIFIED_SECTOR_LABEL`** em `apps/web/lib/constants.ts`. Use estes — não recrie.
- **Cards/rows/header** já mostram "Não classificado" cinza quando `gics_sector` é null. Sem mais fallback PT-BR legado.
- **`buildCompanyHeroModel`** monta `sectorHref` a partir de `company.gics_sector_slug` (não `sector_slug`). Em empresas sem GICS o botão "Ver setor" desabilita corretamente.
- **`apps/web/tests/company-dashboard.test.ts`** já tem mock com `gics_sector_slug="energy"` para o PETROBRAS fixture.

## Decisões já tomadas pelo usuário (não pergunte de novo)

- **Idioma:** GICS oficial em inglês (Energy, Consumer Staples...). Sem tradução PT.
- **Não classificados:** badge "Não classificado" + cinza neutro. Excluídos do filtro e de `/setores`.
- **Sub-indústria:** rotas **nested** `/setores/[sector]/[sub-industry]` (decisão para Fase 3).
- **Slugs CVM legados:** **404** (corte limpo, sem redirect).
- **Estratégia de commit:** o usuário aceita commits únicos que misturem mudanças pré-sessão dele com a sua, desde que o intent fique claro na mensagem.

## O que falta — Fase 3 (próxima)

**Objetivo:** URL canonical `/setores/[sector]/[sub-industry]` para sub-indústrias GICS. Hoje só existe flat `/setores/[slug]` com `?visao=sub_sector` no hub, e os cards de sub-indústria linkam para `/setores/[sub_slug]` (que retorna None em `get_sector_detail` — quebrado hoje).

### Arquivos a tocar

- **Criar** `apps/web/app/setores/[slug]/[sub_slug]/page.tsx`
  - Recebe `slug` (setor GICS) e `sub_slug` (sub-indústria GICS).
  - Valida cadeia: a sub-indústria pertence ao setor declarado. Se não, `notFound()`.
  - Para validar, ou:
    - (a) Chama `fetchSectorDetail(sub_slug)` e checa `parent_sector_slug === slug`, OR
    - (b) Backend ganha um novo método/parâmetro que cross-checa (mais limpo, mais trabalho).
  - Reusa `SectorOverview` / `SectorCompanyTable` existentes; só muda o data fetch + a breadcrumb (Home / Setores / [setor] / [sub-indústria]).

- **`apps/web/app/setores/page.tsx`** (atual hub `?visao=sub_sector`)
  - Quando `groupBy === "sub_sector"`, cards devem linkar para `/setores/${parent_sector_slug}/${sub_slug}` em vez de `/setores/${sub_slug}`.
  - O DTO já carrega `parent_sector_slug` (`src/read_service.py:1218`). Verifique se chega até `apps/web/lib/api.ts:SectorDirectoryItem`.

- **`apps/web/components/sectors/sector-directory-list.tsx`**
  - Ajustar a construção do href para sub-indústrias.

- **`src/contracts.py`** — `SectorDirectoryItem`
  - `parent_sector_name`/`parent_sector_slug` já existem como `Optional`. Tornar **obrigatórios quando `group_type == "sub_sector"`** via `__post_init__` ou docstring. Cuidado: mudança no DTO afeta a bridge serialization.

- **`desktop/bridge.py`** — `get_sector_detail`
  - Considerar adicionar param opcional `parent_sector` para cross-check no backend (alinhar com `read_service.get_sector_detail`).

- **`src/read_service.py`** — `get_sector_detail`
  - Hoje busca por sub-industry slug? Precisa entender o branch. Talvez precise estender para receber `sub_industry_slug` separado de `sector_slug`.

### Verificação Fase 3

```python
# Validar via read_service direto (caminho .exe):
from src.read_service import CVMReadService
svc = CVMReadService()
d = svc.get_sector_detail(sector_slug="brewers", year=None)
# Hoje retorna None. Após Fase 3 deve retornar dados da sub-indústria
# Brewers (3-5 empresas) com parent_sector_slug="consumer-staples".
```

E no UI:
- `/setores?visao=sub_sector` → cards linkam para URLs nested.
- `/setores/consumer-staples/brewers` → carrega só Ambev e similares.
- `/setores/consumer-staples/sub-inexistente` → 404.
- `/setores/energy/brewers` (sub-indústria não pertence ao setor) → 404.

## O que falta — Fase 4 (depois da 3)

Tirar `sector_name`/`sector_slug` legados dos DTOs de **empresa** em `src/contracts.py` (manter nos DTOs de hub setorial, onde já representam GICS). Manter `gics_sector` como `Optional` para suportar catalog fallback.

Detalhes no plano em `C:\Users\jadaojoao\.claude\plans\tender-pondering-russell.md`.

## Comandos úteis

```bash
# Subir backend para preview web (opcional, sabendo do bug):
python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000

# Subir Next dev:
cd apps/web && npm run dev

# Rodar tests:
cd apps/web && npm run test:unit

# Validar GICS direto (caminho .exe):
python -c "from src.read_service import CVMReadService; print(CVMReadService().list_companies(sector_slug='energy', page=1, page_size=3).items)"

# Inspecionar DB:
python -c "import sqlite3; c=sqlite3.connect('data/db/cvm_financials.db'); print(c.execute('SELECT cd_cvm, company_name, gics_sector FROM companies WHERE cd_cvm IN (23264, 9512, 4170)').fetchall())"
```

## Workflow

1. **Pergunte ao usuário** se quer começar pela Fase 3 ou se há outra prioridade que apareceu.
2. **Não toque em `apps/api/`** — se a verificação web preview falhar, isso é esperado.
3. **Verifique no caminho .exe** (read_service direto + tests), não no `next dev`.
4. **Não pergunte sobre decisões já tomadas** (idioma, não classificados, 404, nested routes).
5. **Commit per fase**, não acumule. Mensagens descritivas no estilo dos commits 18fe1a8 e bd7e510.

Pode começar.
