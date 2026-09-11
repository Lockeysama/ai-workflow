#!/usr/bin/env python3
"""Install a repository skill without changing the source or silently overwriting installs."""
import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent.parent


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        if path.is_symlink():
            raise ValueError('技能内包含符号链接，不能安全比较或复制：' + str(path))
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def default_destination(agent):
    if agent == 'codex':
        return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser() / 'skills'
    if agent == 'claude':
        return Path.home() / '.claude' / 'skills'
    raise ValueError('未知目标')


def install(name, destination, replace=False, dry_run=False):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
        raise ValueError('技能名必须为小写字母、数字和连字符。')
    source = ROOT / 'skills' / name
    if not (source / 'SKILL.md').is_file():
        raise ValueError('仓库中不存在技能：' + name)
    destination = Path(destination).expanduser().absolute()
    target = destination / name
    # Do not resolve the last component: a symlink target must be rejected explicitly.
    if target.is_symlink():
        raise ValueError('目标是符号链接，请人工检查：' + str(target))
    resolved = target.resolve()
    if resolved == source.resolve() or source.resolve() in resolved.parents or resolved in source.resolve().parents:
        raise ValueError('安装路径不能与仓库技能源目录重叠。')
    wanted = inventory(source)
    exists = target.exists()
    if exists:
        if not target.is_dir():
            raise ValueError('目标已存在且不是目录：' + str(target))
        if inventory(target) == wanted:
            return '已是相同版本，无需修改：' + str(target)
        if not replace:
            raise ValueError('目标有不同内容，未修改。检查后可使用 --replace（会先备份）：' + str(target))
    if dry_run:
        return ('将备份并替换：' if exists else '将安装：') + str(target)
    destination.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.ai-workflow-', dir=destination.parent))
    backup = None
    try:
        prepared = staging / name
        shutil.copytree(source, prepared, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        if inventory(prepared) != wanted:
            raise ValueError('复制校验失败，未替换已有安装。')
        if exists:
            backup_root = destination.parent / 'ai-workflow-backups'
            backup_root.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup = backup_root / (name + '-' + stamp + '-' + uuid.uuid4().hex[:8])
            target.rename(backup)
        try:
            prepared.rename(target)
        except Exception:
            if backup is not None:
                backup.rename(target)
            raise
    finally:
        shutil.rmtree(staging)
    return '已安装：' + str(target) + ('\n旧版备份：' + str(backup) if backup else '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill', nargs='?', default='human-interface-language')
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument('--agent', choices=('codex', 'claude'), default='codex')
    targets.add_argument('--dest', type=Path, help='目标 skills 父目录；脚本自动添加技能名')
    parser.add_argument('--replace', action='store_true', help='明确替换不同版本，先备份原目录')
    parser.add_argument('--dry-run', action='store_true', help='只检查和显示，不写文件')
    args = parser.parse_args()
    try:
        print(install(args.skill, args.dest or default_destination(args.agent), args.replace, args.dry_run))
    except (ValueError, OSError) as e:
        parser.exit(1, str(e) + '\n')


if __name__ == '__main__':
    main()
