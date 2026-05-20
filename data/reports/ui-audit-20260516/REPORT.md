# UI Audit — Página de Detalhe de Empresa
**Rota:** `/empresas/[cd_cvm]` (capturas em `/empresas/23264` — AMBEV S.A)
**Data:** 2026-05-16
**Stack:** Next 16.2.2 (Turbopack) · React 19 · Tailwind v4 · shadcn (style `base-nova`) · Radix · Base-UI · motion · Hugeicons + lucide

---

## 1 · Métricas

### Core Web Vitals (dev server, sem throttling — referência só de ordem de grandeza)

| Métrica | Valor | Notas |
| --- | --- | --- |
| LCP | **386 ms** (TTFB 143 + render 243) | Ótimo, mas é dev local; em prod com cold cache esperar 2-3× pior |
| CLS | **0.00** | Excelente — skeletons reservam espaço |
| INP | n/a (sem CrUX) | Recomendo medir manualmente em produção |
| FCP | dentro do LCP window | Sem requests render-blocking críticos |

### Lighthouse (desktop, navigation mode)

| Categoria | Score |
| --- | --- |
| Accessibility | **97** |
| Best Practices | **100** |
| SEO | **100** |
| Agentic Browsing | 67 (3 falhas) |

Relatórios brutos: [`report.json`](report.json) / [`report.html`](report.html).

### Network

- **39 requests** no carregamento inicial, todos 200/204.
- Nenhum waterfall problemático (chunks Next/Turbopack carregam em paralelo).
- Sem requests render-blocking de terceiros (não há GA/Sentry/etc).
- `POST /api/company-view` dispara analytics após hidratação — ok.

### Console

- **0 erros, 0 warnings.**

### Bundle

- Não capturado nesta sessão (Turbopack dev não emite analyse stats facilmente). Sugestão: rodar `next build` + `@next/bundle-analyzer` num passo separado — `motion`, `react-day-picker`, `remotion`/`@remotion/player` e `react-countup` são candidatos a investigação (Remotion em particular é grande e o uso dele no detail page não está claro).

---

## 2 · Issues priorizados

### P0 — bloqueia entendimento ou viola contraste

#### P0.1 — Redundância tripla do "Período atual"
A frase **"Período atual: 2023, 2024, 2025"** aparece **duas vezes** em ~120 px de distância vertical:

1. [apps/web/components/company/company-period-preset.tsx:328-335](apps/web/components/company/company-period-preset.tsx#L328) — chip dentro do bloco custom-only.
2. [apps/web/components/company/company-analysis-panel.tsx:89-94](apps/web/components/company/company-analysis-panel.tsx#L89) — pill ao lado do título "Visão anual".

A tabela ainda exibe os anos como cabeçalhos de coluna (3ª "exibição"). **Recomendação:** manter o chip somente no `CompanyAnalysisPanel` (lá faz sentido — comunica o recorte ativo da análise) e remover do wrapper de período. O cabeçalho do período já é implícito pelo formulário DE/ATÉ logo abaixo.

#### P0.2 — `variant="custom-only"` força o form DE/ATÉ aberto sempre
Em [apps/web/app/empresas/[cd_cvm]/page.tsx:189](apps/web/app/empresas/[cd_cvm]/page.tsx#L189) a página instancia `CompanyPeriodPreset` com `variant="custom-only"`. Resultado: o usuário **nunca** vê os presets 3A/5A/Todos definidos em [company-period-preset.tsx:28-37](apps/web/components/company/company-period-preset.tsx#L28). O form custom (com Calendar popover de ano) ocupa ~120 px verticais sempre — para uma ação que muda recorte de leitura, deveria ser secundária.

**Recomendação:** voltar para `variant="full"` (que mostra chips de preset por padrão e abre o custom inline somente quando selecionado), ou colapsar o custom-only num `<Popover>`/`<details>` controlado pelo chip "Período atual".

#### P0.3 — Contraste insuficiente em 2 botões (axe-core via Lighthouse)
Falha de `color-contrast`:
- Botão **"Excel"** no header: [company-header.tsx:82-94](apps/web/components/company/company-header.tsx#L82) — `bbox top:190 left:1044`. O `ExcelDownloadButton` provavelmente herda variante `outline` sobre o gradiente do hero card (linha 49). Texto sobre o gradiente muted-color quebra AA.
- Botão **"Aplicar"** do form de período: [company-period-preset.tsx:207-209](apps/web/components/company/company-period-preset.tsx#L207) — `bbox top:530 left:1172`. Texto branco sobre `primary` no tema atual (provavelmente um amber/yellow) não atinge 4.5:1.

**Recomendação:** verificar tokens `--primary` e `--primary-foreground` no light mode, ou trocar Excel para variant `secondary` com fundo sólido.

#### P0.4 — Label/Accessible-name mismatch em 3 botões
Falha de `label-content-name-mismatch`:
- `Selecionar período inicial` e `Selecionar período final` — [company-period-preset.tsx:253-262](apps/web/components/company/company-period-preset.tsx#L253). Os botões mostram o ano (ex: "2023") como conteúdo, mas o `aria-label` é "Selecionar período inicial". Leitores de tela anunciam algo diferente do que está visível.
- Botão "Hoje" na sidebar de notícias — [company-market-sidebar.tsx:278-285](apps/web/components/company/company-market-sidebar.tsx#L278). Conteúdo visível "Hoje", `aria-label` "Filtrar notícias recentes por data".

**Recomendação:** ou usar `aria-labelledby` apontando ao label visível ("DE:" + valor), ou incluir o valor no aria-label (`aria-label={\`Período inicial: ${value}, abrir seletor\`}`).

---

### P1 — qualidade alta, mas não bloqueante

#### P1.1 — Sidebar de mercado é 100% mock
[company-market-sidebar.tsx:54-100](apps/web/components/company/company-market-sidebar.tsx#L54) gera cotação e notícias **a partir de um seed determinístico do `cd_cvm`**. Ocupa `lg:col-span-4` (33% do viewport) e não tem disclaimer de "dados ilustrativos". Risco regulatório/UX: usuário pensa que R$ 150,82 é preço real.

**Recomendação:**
- Curto prazo: adicionar badge "demonstrativo" ou tooltip; ou esconder atrás de feature flag até ter fonte real.
- Médio prazo: substituir cotação por `<Card>` "Cotação em breve" (mais honesto) e tirar notícias do MVP.

#### P1.2 — Densidade desbalanceada coluna esquerda × sidebar
No desktop 1440px, o `CompanyAnalysisChart` na coluna esquerda (col-span-8) tem muito whitespace vertical entre o eixo X e a tabela, enquanto a sidebar empilha 2 cards densos em col-span-4. Ver `desktop-1440-light.png` / `desktop-1440-dark.png`.

**Recomendação:**
- O chart pode reduzir altura para `h-64` (atualmente parece ~h-96) e os labels de séries (Margem Bruta/EBITDA/EBIT em [company-analysis-panel chart, uid 3_53-55]) podem ir para uma legenda lateral compacta.
- Considerar mover a tabela para baixo da sidebar inteira (grid 12 colunas com chart em col-span-8, sidebar em col-span-4, tabela full-width abaixo). Aproveita o espaço horizontal e melhora a leitura da tabela em telas grandes.

#### P1.3 — Botão "Mais informações" (CompanyHelpTip) usado 5× na fold
Snapshot mostra 5 botões "Mais informacoes" em sequência (uids 3_38, 3_45, 3_47, 3_57 + um na sidebar). Excesso de ícones de ajuda sinaliza que o copy primário não está explicando o suficiente.

**Recomendação:** reduzir para no máximo 2: um no chip de período (explicando recorte) e um na tabela (explicando ordenação). Os outros deveriam estar implícitos no rótulo da seção.

#### P1.4 — Tipografia ALL-CAPS exagerada
Os eyebrows usam `tracking-[0.22em]` e `tracking-[0.26em]`:
- "DETALHE DA COMPANHIA"
- "ANÁLISE DE INDICADORES"
- "TABELA ANUAL"
- "COTAÇÃO"
- "INDICADOR" / "CATEGORIA" / "DELTA YOY" (cabeçalhos de tabela)
- "PRONTA AGORA" / "PLATAFORMA" / "RECURSOS" (rodapé)

São 7+ eyebrows na mesma página. Em `base-nova` style isso vira ruído visual. **Recomendação:** reservar all-caps para eyebrows de seção (máx 2 na página); cabeçalhos de tabela podem ser Sentence case com peso semibold.

#### P1.5 — Hierarquia: H2 "Visão anual" compete com H1 "AMBEV S.A"
A H1 fica no hero card; logo abaixo, depois das tabs e do período, vem outra H2 grande ("Visão anual"). Como o usuário **veio** para ver a análise, faz sentido a análise ter peso visual — mas o eyebrow "ANÁLISE DE INDICADORES" + H2 "Visão anual" + chip "Período atual" + selector de indicadores comprimem 4 elementos numa linha.

**Recomendação:** mesclar eyebrow + H2 em "Análise anual de indicadores" (uma só linha, semibold lg) e eliminar o chip duplicado (ver P0.1).

#### P1.6 — Breadcrumb e tabs muito próximos
Breadcrumb (`Home > Empresas > AMBEV S.A`) está no [company-header.tsx:29-47](apps/web/components/company/company-header.tsx#L29), depois vem hero card grande, depois `CompanyUrlTabs`. As tabs ficam visualmente "soltas" entre o hero e o filtro de período. **Recomendação:** mover as tabs para **dentro do hero card** ou incorporá-las ao topo do container de conteúdo, criando uma âncora visual mais clara.

---

### P2 — polimento

- **P2.1** — Footer com 4 colunas vazias ("KPIs", "Macro", "Screener", "Metodologia", "Glossário" são StaticText, não links). Ou faça funcionar, ou esconda até existir conteúdo.
- **P2.2** — Banner "SLICE PUBLICO V2" no header (`uid 3_17`) parece um eyebrow de DSS; em produção isso confunde — esconder em build prod ou trocar por chip "beta".
- **P2.3** — `CompanyHelpTip` (botões `Mais informacoes`) não tem texto visível; o ícone é só `?` redondo. Tooltips ficam atrás de hover/focus — em mobile não existem. Considerar Popover clicável.
- **P2.4** — Tabela anual com 4 colunas numéricas + 1 delta. Em mobile (`mobile-375-*.png`) faz overflow horizontal forçando scroll lateral. Considerar uma view de "card por indicador" em <md ou um sticky-column.
- **P2.5** — Sparkline do quote card (76 px de altura, `viewBox 224×86`) usa `currentColor` com opacity 0.07 no fill — em dark mode quase invisível, em light mode some no fundo `bg-muted/20`.
- **P2.6** — `text-xs` (12 px) abundante: timeLabel das notícias, source, "Selecione uma data...", footer all-caps. Em telas com escala 100% no Windows fica ilegível. Subir para `text-sm` onde possível.
- **P2.7** — Foco visível: `focus-visible:ring-2 focus-visible:ring-ring` está aplicado consistentemente nos componentes lidos — ok. Validar com teclado os botões do sparkline (`Max/10A/5A/3A/1A`) que usam `<button>` puro sem `<ToggleGroup>`.

---

## 3 · Componentes shadcn candidatos

Registry default `@shadcn` em `components.json` (sem registros customizados ativos). Buscas mostraram catálogo limitado. Recomendações concretas:

| Bloco atual | Substituição sugerida | Por quê |
| --- | --- | --- |
| Sparkline mockado + botões custom de período (`Max/10A/5A/3A/1A`) | `Chart` (shadcn — line chart) + `ToggleGroup` | Acessibilidade nativa (radiogroup), consistência de tokens, suporte a Recharts |
| Calendário ano-único (`PeriodCalendarPicker` → react-day-picker `mode="single"` com `captionLayout="dropdown"`) | `date-picker-with-range` ou um `<Select>` simples de anos | Selecionar 1 ano via calendário é over-engineering — `<Select>` é mais direto |
| Form DE/ATÉ + botão Aplicar | `Slider` dual (range) ou um `Tabs`/`SegmentedControl` com presets | Para no máx ~10 anos, slider de range é mais visual e tem 1 interação só |
| Cards de notícia mockados | Remover do MVP, ou `Card` + `Skeleton` rotulado "Em breve" | Honestidade > densidade falsa |
| `CompanyHelpTip` (5×) | `Tooltip` shadcn padrão + redução de uso | Já é Radix — só padronizar |
| Footer com colunas de links inertes | `nav` simples ou seções escondidas atrás de flags | Reduzir noise |

> Nota: o registry `@shadcn` retornou apenas o exemplo `date-picker-with-range` para nossas queries (`date range picker`, `stat card kpi`, `chart price ticker`, `toggle group segmented`, `empty state news list`). Vale considerar adicionar um registry interno ou um community registry (ex: `@magicui`, `@aceternity`) ao `components.json` se a equipe quiser mais building blocks prontos.

---

## 4 · Quick wins (≤30 min cada)

1. **Remover chip "Período atual" duplicado** — apagar [company-period-preset.tsx:326-336](apps/web/components/company/company-period-preset.tsx#L326). (P0.1)
2. **Trocar `variant="custom-only"` por `"full"`** em [page.tsx:189](apps/web/app/empresas/[cd_cvm]/page.tsx#L189) e validar visual. (P0.2)
3. **Fix `aria-label` dos botões de período** para incluir o valor visível, [company-period-preset.tsx:257](apps/web/components/company/company-period-preset.tsx#L257). (P0.4)
4. **Trocar "Hoje" da sidebar** por `aria-label="Hoje — filtrar notícias por data"` em [company-market-sidebar.tsx:280](apps/web/components/company/company-market-sidebar.tsx#L280). (P0.4)
5. **Adicionar badge "Demonstrativo"** ao quote/news card até integrar dados reais. (P1.1)
6. **Reduzir altura do chart** de `h-96` para `h-64` em `CompanyAnalysisChart`. (P1.2)
7. **Esconder banner "SLICE PUBLICO V2"** em prod (env-flag). (P2.2)
8. **Subir `text-xs` para `text-sm`** em quote subtitle, news meta, footer. (P2.6)

## 5 · Refactors maiores

1. **Período como Popover único** — substituir o card de período por um chip "📅 2023–2025" que abre um Popover com presets + custom inline. Remove ~120 px verticais. Tocar `CompanyPeriodPreset`, `page.tsx`. (~2-3 h)
2. **Reestrutura do grid Overview** — chart em col-span-8, sidebar em col-span-4, tabela full-width abaixo. Tocar `CompanyOverview`, `CompanyAnalysisPanel`. (~2 h + medir antes/depois)
3. **Sidebar real ou esconder** — decisão de produto: ou integrar B3/CVM noticias reais ou remover totalmente. Toca lib/api + sidebar. (4+ h)
4. **Mobile da tabela** — transformar `<table>` em cards repetíveis em <md. Tocar `CompanyAnalysisPanel`. (~3 h)
5. **Padronizar eyebrows** — reduzir all-caps a um único componente `<SectionEyebrow>` e usar no máximo 2 por página. Cross-page. (~4 h)

---

## 6 · Capturas

| Viewport | Light | Dark |
| --- | --- | --- |
| Desktop 1440 | `desktop-1440-light.png` | `desktop-1440-dark.png` |
| Tablet 768 | `tablet-768-light.png` | `tablet-768-dark.png` |
| Mobile 375 | `mobile-375-light.png` | `mobile-375-dark.png` |

Trace de performance: `trace.json` · Lighthouse: `report.html` / `report.json`.

---

## 7 · Limitações deste audit

- Métricas de performance vieram de **dev server local sem throttling**. CWV reais virão só em produção. Recomendo um run de Lighthouse contra preview/prod (`vercel.app` ou similar) para baseline confiável.
- O backend FastAPI (`apps/api`) precisou ser iniciado manualmente — o fluxo padrão de `npm run dev` não levanta a API automaticamente. Vale documentar ou adicionar um `dev:all` no monorepo.
- Bundle size não foi medido (precisa de `next build` + analyzer).
- INP precisa de interação real do usuário — não capturado neste audit estático.
