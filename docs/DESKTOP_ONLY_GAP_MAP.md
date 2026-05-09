# Desktop-Only Gap Map e Fechamento

Data: 2026-05-08  
Escopo: migracao desktop-only no runtime local (`.exe`) sem dependencia de API remota para uso normal.

## 1) Mapa de gaps (arquivo a arquivo)

### `desktop-ready` (fluxo local via bridge consolidado)

- `desktop/bridge.py`  
  Exposicao de leitura, setores, refresh, downloads, health e update via `window.pywebview.api`.
- `apps/web/lib/desktop-bridge.ts`  
  Wrapper tipado para chamadas bridge e contratos de payload.
- `apps/web/components/home/home-desktop-loader.tsx`  
  Home local carregada por bridge.
- `apps/web/components/companies/companies-directory-desktop-loader.tsx`  
  Diretorio local carregado por bridge.
- `apps/web/components/company/company-detail-desktop-loader.tsx`  
  Cockpit local (info/anos/kpis/demonstracoes) carregado por bridge.
- `apps/web/components/sectors/sectors-directory-desktop-loader.tsx`  
  Hub setorial local carregado por bridge.
- `apps/web/components/sectors/sector-detail-desktop-loader.tsx`  
  Detalhe setorial local carregado por bridge.

### `desktop-partial` (dual path desktop + web, sem bloqueio critico)

- `apps/web/lib/api.ts`  
  Camada unificada com fallback HTTP para web e bridge para desktop em quase todos os fluxos.
- `apps/web/lib/download-file.ts`  
  Download desktop via bridge para empresa/lote; fallback web por endpoint.
- `apps/web/app/page.tsx`, `apps/web/app/empresas/page.tsx`, `apps/web/app/empresas/[cd_cvm]/page.tsx`, `apps/web/app/setores/page.tsx`, `apps/web/app/setores/[slug]/page.tsx`, `apps/web/app/atualizar-base/page.tsx`
  Rotas usam `isDesktopServerMode()` para desviar para loaders locais.
- `apps/web/next.config.ts`  
  Runtime local ainda baseado em `output: "standalone"` (Node embutido).

### `web-only-blocker` (dependencia web que impactava runtime local)

- `apps/web/lib/api.ts` (`fetchCompanyFreshness`)  
  Antes: sempre via HTTP `/refresh-status`, sem branch desktop local no helper especifico.
  Impacto: telas de freshness/no-data podiam depender de API no modo local.
  Status: **resolvido nesta entrega**.

## 2) Priorizacao dos bloqueios

1. `fetchCompanyFreshness` em `apps/web/lib/api.ts`  
   - risco: alto (atinge cards de frescor e UX de no-data)  
   - esforco: baixo  
   - acao: migrar para bridge em desktop e impedir HTTP no server desktop.

2. Route handlers em `apps/web/app/api/**`  
   - risco: medio (nao bloqueiam desktop quando loaders locais estao ativos)  
   - esforco: medio/alto (dependencias de build web e testes)  
   - acao: manter no dual-target; remover apenas quando decidir abandonar web runtime.

3. `output: "standalone"` em `apps/web/next.config.ts`  
   - risco: baixo imediato, estrategico no longo prazo  
   - esforco: alto para migrar para export estatico completo  
   - acao: decidir apos fechamento dos gaps funcionais.

## 3) Sequencia de fechamento (bridge-first)

1. Fechar helpers de dominio ainda HTTP-only no desktop (`freshness` concluido).  
2. Validar todos os fluxos criticos desktop: home, empresas, detalhe, setores, atualizar-base.
3. Congelar contrato bridge como fonte local de verdade para o runtime desktop.  
4. Manter `app/api/**` apenas como camada web enquanto existir dual-target.

## 4) Decisao arquitetural (com base no gap map atual)

Decisao desta etapa: **manter Next standalone + Node embutido no curto prazo**.

Justificativa:

- o gap funcional critico identificado era de contrato (`freshness`) e foi resolvido sem alterar arquitetura macro;
- o caminho standalone ja esta operacional no build/release atual;
- migrar para export estatico agora aumentaria escopo e risco sem ganho imediato para o objetivo desktop-only funcional.

Condicao para revisitar:

- apos dois ciclos de smoke desktop estavel, reavaliar export estatico com foco em boot footprint e simplificacao operacional.

## 5) Gates de build reproduzivel (desktop)

Checklist minimo por release desktop:

1. Build local:
   - `desktop/build_desktop.ps1`
   - confirmar geracao de `dist/CVMAnalytics/CVMAnalytics.exe`
2. Runtime smoke (maquina limpa ou equivalente):
   - abrir app
   - navegar: `/`, `/empresas`, `/empresas/[cd_cvm]`, `/setores`, `/setores/[slug]`, `/atualizar-base`
   - testar refresh on-demand/batch
   - testar download excel (empresa e lote)
3. Release CI:
   - `.github/workflows/release-desktop.yml` com tag de versao
   - validar artefatos zip + checksum

## 6) Mudancas aplicadas nesta entrega

- `apps/web/lib/desktop-bridge.ts`
  - adicionado `bridgeFetchCompanyFreshness(cdCvm)`.
- `apps/web/lib/api.ts`
  - `fetchCompanyFreshness(cdCvm)` agora:
    - usa bridge quando `isDesktopMode()`;
    - evita dependencia HTTP quando `isDesktopServerMode()`.

