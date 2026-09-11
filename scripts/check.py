#!/usr/bin/env python3
"""Repository checks, no network or third-party dependencies."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def run(*args):
    subprocess.run([sys.executable, '-B', *map(str, args)], cwd=ROOT, check=True,
                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


def main():
    skills = sorted((ROOT/'skills').glob('*/SKILL.md'))
    assert skills, 'No skills found'
    for entry in skills:
        text = entry.read_text(encoding='utf-8')
        frontmatter = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
        assert frontmatter, f'Missing frontmatter: {entry}'
        name = re.search(r'^name:\s*([a-z0-9-]+)\s*$', frontmatter[1], re.M)
        assert name and name[1] == entry.parent.name, f'Invalid skill name: {entry}'
        assert re.search(r'^description:\s*\S', frontmatter[1], re.M), f'Missing description: {entry}'
        for doc in [entry, *sorted((entry.parent/'references').glob('*.md'))]:
            for link in re.findall(r'\]\(([^)]+)\)', doc.read_text(encoding='utf-8')):
                if '://' not in link and not link.startswith('#'):
                    assert (doc.parent/link.split('#')[0]).exists(), f'Broken local link: {doc}: {link}'
        for path in entry.parent.rglob('*'):
            if path.is_file() and path.suffix in ('.py', '.md', '.yaml', '.html'):
                assert '/Users/chenyitao/' not in path.read_text(encoding='utf-8'), f'Personal path: {path}'
    run('skills/human-interface-language/scripts/test_hil.py')
    run('-m', 'unittest', 'discover', '-s', 'tests', '-v')
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)/'example.html'
        script = ROOT/'skills/human-interface-language/scripts/hil.py'
        run(script, 'render', '--content', ROOT/'examples/hil-body.html', '--title', 'HIL 示例', '--output', output)
        run(script, 'check', output)
    print('All repository checks passed.', flush=True)


if __name__ == '__main__':
    main()
