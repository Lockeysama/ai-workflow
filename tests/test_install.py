import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / 'agent' / 'skills'
        self.name = 'human-interface-language'

    def test_dry_run_does_not_write(self):
        installer.install(self.name, self.destination, dry_run=True)
        self.assertFalse(self.destination.exists())

    def test_copy_and_repeat(self):
        installer.install(self.name, self.destination)
        self.assertEqual(installer.inventory(ROOT/'skills'/self.name), installer.inventory(self.destination/self.name))
        before = (self.destination/self.name/'SKILL.md').stat().st_mtime_ns
        installer.install(self.name, self.destination)
        self.assertEqual(before, (self.destination/self.name/'SKILL.md').stat().st_mtime_ns)

    def test_conflict_preserved_and_replace_backed_up(self):
        installer.install(self.name, self.destination)
        modified = self.destination/self.name/'SKILL.md'
        modified.write_text('local changes', encoding='utf-8')
        with self.assertRaises(ValueError):
            installer.install(self.name, self.destination)
        self.assertEqual(modified.read_text(), 'local changes')
        installer.install(self.name, self.destination, replace=True, dry_run=True)
        self.assertFalse((self.destination.parent/'ai-workflow-backups').exists())
        installer.install(self.name, self.destination, replace=True)
        backups = list((self.destination.parent/'ai-workflow-backups').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0]/'SKILL.md').read_text(), 'local changes')
        self.assertEqual(installer.inventory(ROOT/'skills'/self.name), installer.inventory(self.destination/self.name))

    def test_reject_symlink(self):
        self.destination.mkdir(parents=True)
        (self.destination/self.name).symlink_to(ROOT/'skills'/self.name, target_is_directory=True)
        with self.assertRaises(ValueError):
            installer.install(self.name, self.destination, replace=True)

    def test_invalid_skill_and_source_overlap(self):
        for name in ('../human-interface-language', 'missing-skill'):
            with self.assertRaises(ValueError):
                installer.install(name, self.destination)
        with self.assertRaises(ValueError):
            installer.install(self.name, ROOT/'skills')

    def test_codex_environment_and_custom_destination(self):
        with patch.dict(os.environ, {'CODEX_HOME': str(Path(self.temp.name)/'custom-codex')}):
            self.assertEqual(installer.default_destination('codex'), Path(self.temp.name)/'custom-codex'/'skills')
        installer.install(self.name, self.destination/'custom')
        self.assertTrue((self.destination/'custom'/self.name/'SKILL.md').is_file())

    def test_failed_install_restores_backup(self):
        installer.install(self.name, self.destination)
        modified = self.destination/self.name/'SKILL.md'
        modified.write_text('local changes', encoding='utf-8')
        original_rename = Path.rename

        def fail_prepared(source, target):
            if source.parent.name.startswith('.ai-workflow-'):
                raise OSError('simulated install failure')
            return original_rename(source, target)

        with patch.object(Path, 'rename', fail_prepared):
            with self.assertRaises(OSError):
                installer.install(self.name, self.destination, replace=True)
        self.assertEqual(modified.read_text(), 'local changes')


if __name__ == '__main__':
    unittest.main()
