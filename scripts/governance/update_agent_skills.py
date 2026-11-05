"""Verify vendored skills offline or update their pinned upstream snapshots."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2] / '.agents' / 'skills'


def safe_path(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or '\\' in relative or ':' in relative or relative.startswith('/') or '..' in parts:
        raise ValueError(f'Unsafe path: {relative}')
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError(f'Path escapes installation: {relative}')
    return path


def hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}


def verify(root: Path, manifest: dict) -> None:
    for skill in manifest['skills']:
        folder = safe_path(root, skill['name'])
        files = {p.relative_to(folder).as_posix(): p.read_bytes()
                 for p in folder.rglob('*') if p.is_file()}
        for name in files:
            safe_path(folder, name)
        if hashes(files) != skill['sha256']:
            raise ValueError(f"Local files differ from manifest: {skill['name']}")
        if 'SKILL.md' not in files:
            raise ValueError(f"Missing SKILL.md: {skill['name']}")


def download(url: str) -> bytes:
    headers = {'User-Agent': 'CVMAnalytics-skill-maintenance'}
    token = os.environ.get('GH_TOKEN')
    if token and url.startswith('https://api.github.com/'):
        headers['Authorization'] = f'Bearer {token}'
    with urlopen(Request(url, headers=headers), timeout=60) as response:
        return response.read()


def fetch_upstream(skill: dict) -> tuple[str, dict[str, bytes]]:
    repo = skill['repository']
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('Invalid upstream repository')
    api = f'https://api.github.com/repos/{repo}'
    commit = json.loads(download(f'{api}/commits/main'))['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid upstream commit')
    tree = json.loads(download(f'{api}/git/trees/{commit}?recursive=1'))
    if tree.get('truncated'):
        raise ValueError('Upstream tree is truncated')
    prefix = skill['source_path'] + '/'
    files = {}
    for entry in tree['tree']:
        if entry['type'] != 'blob' or not entry['path'].startswith(prefix):
            continue
        if entry['mode'] not in ('100644', '100755'):
            raise ValueError('Upstream symlinks are not supported')
        content = download(f"https://raw.githubusercontent.com/{repo}/{commit}/{entry['path']}")
        blob = hashlib.sha1(f'blob {len(content)}\0'.encode() + content).hexdigest()
        if blob != entry['sha']:
            raise ValueError(f"Upstream blob mismatch: {entry['path']}")
        files[entry['path'][len(prefix):]] = content
    return commit, files


def update(root: Path) -> None:
    manifest_path = root / 'installation-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    verify(root, manifest)
    prepared = []
    # Fetch and validate every package before changing any installed file.
    for skill in manifest['skills']:
        commit, files = fetch_upstream(skill)
        folder = safe_path(root, skill['name'])
        for relative in files:
            path = safe_path(folder, relative)
            if path.is_dir():
                raise ValueError(f'Upstream file replaces an installed directory: {relative}')
        text = files.get('SKILL.md', b'').decode('utf-8')
        if not text.startswith('---\n') or f"name: {skill['name']}\n" not in text:
            raise ValueError(f"Missing or renamed upstream skill: {skill['name']}")
        if hashes(files) != skill['sha256']:
            prepared.append((skill, commit, files))
    if not prepared:
        print('All installed skills are current; no changes.')
        return
    for skill, commit, files in prepared:
        folder = safe_path(root, skill['name'])
        for old in set(skill['sha256']) - set(files):
            safe_path(folder, old).unlink()
        for relative, content in files.items():
            path = safe_path(folder, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        skill['commit'] = commit
        skill['sha256'] = hashes(files)
        print(f"Updated {skill['name']} to {commit}")
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    verify(root, manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='Verify local hashes without network access')
    args = parser.parse_args()
    if args.verify:
        verify(ROOT, json.loads((ROOT / 'installation-manifest.json').read_text(encoding='utf-8')))
        print('All installed skill files match the manifest.')
    else:
        update(ROOT)
