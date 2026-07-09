# Product

## Register

product

## Users

Analistas de mercado financeiro em Equity, Credit, IB e areas relacionadas, alem de investidores analiticos que precisam comparar companhias brasileiras, ler indicadores historicos, validar demonstracoes e decidir onde aprofundar uma analise. O contexto de uso e concentrado: desktop, dados densos, verificacao de periodos, empresas, setores, ativos operacionais e sinais financeiros.

## Product Purpose

CVM Analytics transforma demonstracoes financeiras publicas da CVM em uma experiencia local, consultavel e auditavel. O produto existe para reduzir atrito entre dado bruto regulatorio e leitura financeira confiavel: encontrar empresas, inspecionar indicadores, conferir demonstracoes, atualizar a base local e manter rastreabilidade suficiente para sustentar decisoes analiticas.

## Core Product Principle: Minimalism

Minimalismo e um principio central do CVMAnalytics.

Neste produto, minimalismo nao significa reduzir funcionalidades ou esconder informacao importante. Significa mostrar a informacao certa com hierarquia forte, baixo atrito, padroes consistentes e sem ruido visual ou textual desnecessario.

Decisao de design: menos e mais util quando reduz escolhas visiveis, labels repetidos, containers decorativos e texto generico. Menos nao e util quando remove fonte, periodo, unidade, metodo, caveat, estado ou proxima acao necessaria para o analista confiar no resultado.

A interface deve ajudar o analista a ir rapidamente de:

- selecao da companhia, setor, carteira ou ativo;
- dado de origem;
- indicador;
- tendencia historica;
- interpretacao financeira;
- exportacao ou proxima acao.

Regras praticas:

- Ser direto sem remover contexto material.
- Preferir layouts densos, legiveis e profissionais a dashboards decorativos.
- Mostrar resumo primeiro e detalhe sob demanda.
- Evitar labels repetidos, textos auxiliares vagos, cards redundantes e padroes genericos de dashboard.
- Tratar paineis redundantes como erro de produto: um resumo so deve existir se adicionar decisao, acao ou drill-down de fonte/metodo que a tela ainda nao oferece.
- Padronizar tabelas, indicadores, filtros e graficos entre paginas.
- Preservar auditabilidade: fonte, periodo, unidade, moeda, consolidacao e metodo de calculo devem permanecer acessiveis.
- Nunca esconder falhas, dados ausentes, fontes parciais ou problemas de qualidade para deixar a tela "limpa".
- Estados vazios, carregando e erro devem ser explicitos, uteis e proximos do componente afetado.
- A interface deve apoiar julgamento profissional rapido, nao navegacao casual.

## Brand Personality

Tecnico e auditavel, preciso, sobrio e premium. A interface deve transmitir confianca operacional, dominio financeiro e cuidado com detalhe, sem parecer decorativa ou promocional.

## Anti-references

Nao deve parecer um dashboard SaaS generico, uma landing page de fintech, um painel cripto neon, uma planilha corporativa crua ou uma ferramenta que sacrifica rastreabilidade por graficos vistosos.

## Design Principles

- Clareza antes de impacto: destacar hierarquia, periodo, fonte e estado dos dados antes de efeitos visuais.
- Minimalismo operacional: remover ruido visual e textual, mantendo informacao material, auditabilidade e caminhos claros para aprofundar.
- Densidade com controle: permitir leitura comparativa rica sem sobrecarregar o usuario com adornos ou duplicidade de controles.
- Auditoria visivel: estados, filtros, cobertura, erros e origem dos dados devem ser compreensiveis quando importam para a decisao.
- Sobriedade premium: usar o tema escuro, acentos e espacamento para criar foco e confianca, nao espetaculo.
- Fluxos locais confiaveis: otimizar para uso desktop com SQLite local e comportamento previsivel mesmo sem depender de servicos remotos.

## Page Review Workflow

Quando uma pagina for revisada, o trabalho deve ser incremental e baseado na implementacao real. O agente deve:

1. Inspecionar a rota, componentes ativos, facades de dados e estados existentes.
2. Comparar a pagina com o principio de minimalismo operacional.
3. Separar o essencial, o contexto secundario e o detalhe opcional.
4. Propor mudancas pequenas e direcionadas antes de qualquer redesenho amplo.
5. Preservar fluxos funcionais, dados existentes, fontes, exportacoes e estados de erro.
6. Validar carregamento, vazio, erro, dados parciais, responsividade e performance percebida.
7. Reportar riscos, suposicoes e incertezas que afetem decisao de produto ou qualidade dos dados.

## Accessibility & Inclusion

Mirar WCAG AA para texto normal, controles, foco visivel e limites de componentes. Graficos e indicadores nao devem depender apenas de cor: legendas, labels, tooltips e estados textuais precisam sustentar a compreensao. Respeitar preferencia por movimento reduzido e manter navegacao por teclado em filtros, seletores, abas e tabelas.
