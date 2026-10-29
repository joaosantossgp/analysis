# ADR-0006 — Autenticação local para o app desktop CVM Analytics

**Data:** 2026-05-03
**Status:** Historico — **Não implementado (deferido) em v0.17.0**; revalidar contra `docs/reference/repository-map.md`
**Autor:** Claude (ops-quality, issue #240)
**Contexto completo:** ~~`docs/AUTH_DESKTOP_READINESS.md`~~ (removido em `8506bd9`)

> [!NOTE]
> **Reconciliação de status (auditoria v0.17.0).** A decisão registrada aqui foi
> aceita como abordagem *quando* a autenticação for solicitada, mas a
> implementação nunca ocorreu. Em `v0.17.0`:
> - O bridge `CVMBridge` não expõe método `login()` nem mantém estado
>   `_authenticated`.
> - Não existe rota `/login` em `apps/desktop-web/`.
> - Nenhum arquivo `auth.json` é gerado ou consumido.
> - O contexto original menciona "pywebview + Next.js standalone"; o runtime
>   legado foi removido do pacote desktop na Fase 5B (`v0.15.0`) e o app
>   Next.js foi removido da arvore ativa depois disso.
>
> O ADR permanece preservado como registro histórico da decisão para o caso de
> a autenticação ser priorizada no futuro. Para reativar, revalidar a Abordagem A
> contra o stack atual (pywebview + Vite estático) antes de
> implementar.

---

## Contexto

O app desktop não tem autenticação. O dono quer garantir que o stack (pywebview +
Next.js standalone) não bloqueia adicionar auth no futuro. Este ADR documenta a decisão
de abordagem para quando a implementação for solicitada.

## Decisão

**Abordagem A — PIN local único armazenado em `~/.cvm-analytics/auth.json`.**

## Justificativa

1. **Adequada ao design atual**: o app é single-user por design. SQLite local, sem backend remoto.
   Um PIN protege contra acesso casual sem superdimensionar a solução.

2. **Esforço mínimo**: ~40 linhas no bridge + 1 página `/login` + 1 hook + 1 guard de layout.
   Sem dependências externas novas (SHA-256 via stdlib).

3. **Sem breaking changes no bridge**: o método `login()` é adicionado ao `CVMBridge`
   sem alterar a assinatura dos métodos existentes. JS continua usando `callBridge` com
   a mesma interface — apenas não consegue avançar sem autenticar primeiro.

4. **Caminho de migração para multi-user preservado**: se o produto precisar de múltiplos
   usuários, a Abordagem B (auth_users.json + bcrypt + session token) reutiliza a estrutura
   introduzida pela A (`login()`, `_authenticated`) com extensão incremental.

## Consequências

- **Positivo**: proteção de acesso com custo mínimo de implementação.
- **Positivo**: zero dependências novas para o caso base (SHA-256).
- **Negativo**: não protege os dados em disco (SQLite permanece sem criptografia).
- **Negativo**: sem suporte a múltiplos usuários (aceito — fora do escopo atual).
- **Negativo**: PIN simples com SHA-256. Para ameaças mais sérias, trocar por bcrypt
  (dependência adicional) na implementação real.

## Alternativas rejeitadas

| Abordagem | Por quê rejeitada |
|---|---|
| B — Multi-user + bcrypt + session token | Superdimensionado para app single-user; 3x o esforço |
| C — OS identity (`getpass.getuser()`) | Sem controle de senha; proteção insuficiente em PC compartilhado |

## Pontos de extensão

Para migrar de A para B quando necessário:
1. Substituir `auth.json` por `auth_users.json` com lista de usuários.
2. Trocar `_authenticated: bool` por `_sessions: set[str]` no bridge.
3. Adicionar injeção de `session_token` no `callBridge` do TS.
4. O contrato JS do bridge (assinatura dos métodos de dados) não muda.
