# On-Demand Release Evidence

Este checklist define a barra minima para mudancas estrategicas no fluxo
on-demand. Ele complementa os gates automatizados; nao substitui testes.

## Quando usar

Use este checklist em PRs que alterem busca/entrada, detalhe de companhia sem
dados, polling/wait state, handoff de sucesso, outcomes terminais, mensagens de
freshness ou continuidade mobile do fluxo on-demand.

Mudancas sem impacto no on-demand podem apenas declarar "nao aplicavel" no PR.

## Gates automatizados

O workflow `CI` deve passar nos gates ativos:

- Python core tests: `pytest tests -q`.
- Vite desktop UI typecheck: `npm run typecheck` em `apps/desktop-web`.
- Vite desktop UI build: `npm run build` em `apps/desktop-web`.

Quando a mudanca tocar `apps/api`, rode tambem `pytest apps/api/tests -q`.
Quando a mudanca tocar UI observavel, valide o fluxo no desktop/Vite dev shell.

## Smoke Atualizar Base (`/atualizar-base`)

PRs que alterem o fluxo de atualizacao em lote da pagina **Atualizar base**, a API
`POST /refresh/batch`, jobs `GET /refresh/jobs/{job_id}` ou o bridge desktop
(`request_refresh` / `get_refresh_status` / `cancel_refresh`) devem anexar
evidencia do CLI dedicado **sem** disparar um batch amplo por engano.

Script: `scripts/diagnostics/update_base_smoke.py`.

### Comportamento seguro (default)

- Sem `--confirm-live`, o script **nao** chama API nem bridge; use `--dry-run`
  explicitamente para imprimir o payload (`mode=missing`, `limit=1` por padrao).
- Execucao real exige `--confirm-live`. `limit` acima de **50** exige tambem
  `--allow-large-batch`.
- Variavel `API_BASE_URL` (ou `--api-base`) define a base da FastAPI local/remota.

### Comandos recomendados

Dry-run (somente evidencia do body; nenhuma chamada HTTP):

```powershell
python scripts/diagnostics/update_base_smoke.py --dry-run --mode missing --limit 1
```

Live minimo contra API local (ajuste `--cd-cvm` para um codigo real da sua base):

```powershell
python scripts/diagnostics/update_base_smoke.py --profile web --confirm-live --limit 1 --cd-cvm 9512
```

Mesmo escopo via bridge desktop (Python, sem abrir pywebview):

```powershell
python scripts/diagnostics/update_base_smoke.py --profile desktop --confirm-live --limit 1 --cd-cvm 9512
```

Saida JSON para colar em PR/issue:

```powershell
python scripts/diagnostics/update_base_smoke.py --dry-run --json
```

Validacao automatizada local dos guardrails e fluxos mockados:

```powershell
python -m pytest scripts/diagnostics/test_update_base_smoke.py -q
```

## Checklist de aceitacao

- Search/entry: busca da home chega ao destino certo sem CORS ou
  chamada direta para host externo.
- Wait/polling: estados `queued`, `running`, reconnecting e delayed mantem
  feedback nao destrutivo e caminho de recuperacao.
- Success handoff: sucesso tecnico so vira sucesso de leitura quando existe
  `has_readable_current_data` ou sinal equivalente.
- Mobile continuity: navegacao essencial continua acessivel no viewport mobile.
- Terminal outcomes: `success`, `no_data`, `error`, stalled e already-current
  mostram copy e CTA coerentes.
- Mixed readable outcomes: erro/no-data retryable preserva a leitura existente
  quando `has_readable_current_data=true`.
- CI evidence: linkar o run do workflow `CI` com Python core e Vite desktop UI verdes.
- Manual evidence: anexar screenshot/trace apenas quando a PR muda UI visivel
  ou comportamento de navegacao que o smoke nao consegue demonstrar sozinho.

## Evidencia minima no PR

Inclua no corpo ou comentario final do PR:

- Issue/task vinculada.
- Comandos locais executados, quando aplicavel.
- Link para o run de CI.
- Resultado dos gates de on-demand.
- Riscos ou lacunas assumidas, incluindo itens future-stage only.

## Future-stage only

Nao bloquear releases atuais por itens que ainda nao existem no produto:

- progresso realtime por SSE/websockets;
- notificacoes email, push ou inbox;
- session replay ou analytics pagos;
- historico detalhado de jobs para usuario final.
