#!/usr/bin/env pwsh
# fix-git-config.ps1
# Corrige a inconsistência que quebra o Antigravity no repositório analisys
# Roda quando o Antigravity não responde neste repositório

$repo = $PSScriptRoot

Write-Host "`n🔍 Verificando configuração git em: $repo`n"

# 1. Check repositoryformatversion vs extensions
$format = git -C $repo config core.repositoryformatversion
$wtcfg  = git -C $repo config extensions.worktreeconfig 2>$null

if ($format -eq "0" -and $wtcfg) {
    Write-Host "❌ Encontrado: extensions.worktreeconfig=$wtcfg com repositoryformatversion=0"
    Write-Host "   → Removendo extensão incompatível..."
    git -C $repo config --local --unset extensions.worktreeconfig
    Write-Host "   ✅ Corrigido!`n"
} else {
    Write-Host "✅ Configuração git OK (format=$format, worktreeconfig=$wtcfg)`n"
}

# 2. Check for leftover worktrees
$worktrees = git -C $repo worktree list 2>$null | Where-Object { $_ -notmatch "\[main\]" -and $_ -notmatch "\[master\]" }
if ($worktrees) {
    Write-Host "⚠️  Worktrees ativos encontrados (criados pelo Claude Code):"
    $worktrees | ForEach-Object { Write-Host "   $_" }
    Write-Host ""
    $resp = Read-Host "Remover todos os worktrees acima? (s/n)"
    if ($resp -eq "s") {
        $worktrees | ForEach-Object {
            $path = ($_ -split '\s+')[0]
            Write-Host "   Removendo: $path"
            git -C $repo worktree remove --force $path 2>&1
        }
        git -C $repo worktree prune
        # Clean empty dirs
        $wtDir = Join-Path $repo ".claude\worktrees"
        if (Test-Path $wtDir) {
            Get-ChildItem $wtDir -Directory | ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
        }
        Write-Host "   ✅ Worktrees removidos!`n"
    }
} else {
    Write-Host "✅ Nenhum worktree extra encontrado`n"
}

Write-Host "🔄 Reinicie o Antigravity (feche e abra a pasta novamente)`n"
