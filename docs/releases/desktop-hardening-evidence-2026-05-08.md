# Desktop Hardening Evidence - 2026-05-08

## Escopo validado

- Tipo de mudanca: hardening de build reproduzivel + smoke desktop-only.
- Runtime alvo: `dist/CVMAnalytics/CVMAnalytics.exe`.
- Rotas criticas alvo:
  - `/`
  - `/empresas`
  - `/empresas/[cd_cvm]`
  - `/setores`
  - `/setores/[slug]`
  - `/comparar`
  - `/atualizar-base`

## Evidencia automatizada

### Build desktop

- Comando:
  - `powershell -ExecutionPolicy Bypass -File desktop/build_desktop.ps1 -SkipNextBuild`
- Resultado: sucesso (`exit_code: 0`).
- Artefato:
  - `dist/CVMAnalytics/CVMAnalytics.exe`
- Tamanho total reportado da pasta:
  - ~`92 MB`
- Metadado do executavel:
  - `Length`: `20439864`
  - `LastWriteTime`: `2026-05-08 11:18:01`
- Checksum:
  - `SHA256 97EB4EAF955B81B5A386C850C0B3051E738F2EBF8E18994311C9F8250E924541`

### Smokes e testes locais

- Runtime/bridge smoke:
  - `python -m pytest tests/test_desktop_runtime_paths.py tests/test_bridge_refresh.py tests/test_cvm_pyqt_app.py -q`
  - Resultado: `21 passed`
- API/bridge unit focal:
  - `node --experimental-strip-types --experimental-specifier-resolution=node --test tests/api-client.test.ts tests/desktop-bridge.test.ts`
  - Resultado: `39 passed`
- Update-base smoke script:
  - `python scripts/update_base_smoke.py --dry-run --mode missing --limit 1`
  - Resultado: dry-run ok (sem chamada HTTP)
- Guardrails do smoke script:
  - `python -m pytest scripts/test_update_base_smoke.py -q`
  - Resultado: `9 passed`

## Checklist manual guiado (exe)

Status esperado: marcar cada item com `ok` ou `falha` apos validacao manual no app empacotado.

- [ ] **Boot app**
  - Abrir `dist/CVMAnalytics/CVMAnalytics.exe` e confirmar janela inicial sem erro fatal.
- [ ] **Home (`/`)**
  - Buscar empresa no hero e validar navegacao para detalhe.
- [ ] **Empresas (`/empresas`)**
  - Validar busca, filtro setorial e paginacao.
- [ ] **Detalhe empresa (`/empresas/[cd_cvm]`)**
  - Validar anos, aba visao geral, aba demonstracoes, card freshness.
- [ ] **Setores (`/setores`)**
  - Validar listagem e entrada em detalhe setorial.
- [ ] **Setor detalhe (`/setores/[slug]`)**
  - Validar seletor de ano e alternancia de abas.
- [ ] **Comparar (`/comparar`)**
  - Selecionar empresas, validar KPIs e fallback quando nao houver interseccao.
- [ ] **Atualizar base (`/atualizar-base`)**
  - Abrir tela, iniciar fluxo controlado (escopo minimo), acompanhar status.
- [ ] **Downloads**
  - Download Excel individual e lote zip.
- [ ] **Update prompt**
  - Verificar se check/update nao quebra a navegacao.

## Observacoes

- Warnings nao-bloqueantes vistos no build envolvendo `sharp/libvips` no bundle Next standalone.
- Nao houve falha de build nem falha nos smokes automatizados associados.

## Lacunas aceitas

- Evidencia visual (screenshots da UI empacotada) ainda pendente nesta rodada.
- Falta executar checklist manual completo no `.exe` em sessao interativa.
