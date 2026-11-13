import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from duhe.storage import Store
from duhe.rules import new_game


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'game.db')
        self.cid = self.store.create('alice', new_game(mode='demo'))

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, operation='a'):
        c = self.store.campaign('alice', self.cid)
        return self.store.commit('alice', self.cid, c['current_node'], c['revision'], operation,
                                 new_game(mode='demo'), 'story', {'kind': 'test'}, {'version': 'v1'})

    def test_owner_and_restart(self):
        with self.assertRaises(PermissionError):
            self.store.campaign('bob', self.cid)
        self.commit()
        reopened = Store(self.root / 'game.db')
        self.assertEqual(reopened.node('alice', self.cid)['text'], 'story')
        self.assertEqual(reopened.node('alice', self.cid)['state']['mode'], 'demo')

    def test_replay_and_concurrent_revision(self):
        c = self.store.campaign('alice', self.cid)
        def write(op):
            try:
                return self.store.commit('alice', self.cid, c['current_node'], 0, op,
                                         {'mode': 'demo'}, op, {})['id']
            except ValueError:
                return None
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(write, ['a', 'b']))
        self.assertEqual(sum(x is not None for x in results), 1)
        winner = 'a' if results[0] else 'b'
        self.assertEqual(write(winner), next(x for x in results if x))
        self.assertEqual(len(self.store.nodes('alice', self.cid)), 2)

    def test_branch_history_and_image_completion(self):
        root = self.store.node('alice', self.cid)
        first = self.commit('first')
        self.store.select('alice', self.cid, root['id'])
        second = self.commit('second')
        self.store.set_image('alice', self.cid, first['id'], {'status': 'SUCCEEDED', 'path': 'old.png'})
        self.assertEqual([x['id'] for x in self.store.history('alice', self.cid)], [root['id'], second['id']])
        self.assertIsNone(self.store.node('alice', self.cid)['image'])
        self.assertEqual(self.store.node('alice', self.cid, first['id'])['image']['path'], 'old.png')
        self.assertEqual(self.store.campaign('alice', self.cid)['revision'], 3)

    def test_export_import_images_and_feedback(self):
        n = self.commit()
        image = self.root / 'download.png'
        image.write_bytes(b'PNG-test')
        self.store.set_image('alice', self.cid, n['id'], {'status': 'SUCCEEDED', 'path': str(image)})
        self.store.feedback('alice', self.cid, n['id'], {'rating': 5, 'prompt_version': 'v1'})
        bundle = self.store.export_bundle('alice', self.cid, self.root)
        image.unlink()
        imported = self.store.import_bundle('bob', bundle)
        self.assertNotEqual(imported, self.cid)
        saved = self.store.node('bob', imported)
        self.assertEqual(Path(saved['image']['path']).read_bytes(), b'PNG-test')
        self.assertEqual(saved['state']['mode'], 'demo')
        with self.assertRaises(PermissionError):
            self.store.campaign('alice', imported)

    def test_reject_zip_traversal_and_cycle(self):
        bundle = self.store.export_bundle('alice', self.cid, self.root)
        with zipfile.ZipFile(bundle) as z:
            data = json.loads(z.read('manifest.json'))
        for bad_name, cycle in [('../evil', False), ('safe.txt', True)]:
            if cycle:
                data['nodes'][0]['parent_id'] = data['nodes'][0]['id']
            bad = self.root / ('bad' + str(cycle) + '.zip')
            with zipfile.ZipFile(bad, 'w') as z:
                z.writestr('manifest.json', json.dumps(data))
                z.writestr(bad_name, 'unsafe')
            with self.assertRaises(ValueError):
                self.store.import_bundle('bob', bad)


if __name__ == '__main__':
    unittest.main()

class FeedbackTests(unittest.TestCase):
    def test_feedback_versions_are_queryable_and_owner_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'feedback.db')
            cid = store.create('alice', {'mode': 'normal', 'schema': 1})
            node = store.node('alice', cid)
            fid = store.feedback('alice', cid, node['id'], {'confirmed': True, 'observation': 'silver hair'})
            rows = store.feedbacks('alice', cid, node['id'])
            self.assertEqual(rows[0]['id'], fid)
            self.assertEqual(rows[0]['data']['observation'], 'silver hair')
            self.assertTrue(rows[0]['created_at'])
            with self.assertRaises(PermissionError):
                store.feedbacks('bob', cid)

class ArchiveEdgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'db.sqlite')
        self.cid = self.store.create('alice', new_game())

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent_images_are_explicitly_skipped(self):
        n = self.store.node('alice', self.cid)
        self.store.set_image('alice', self.cid, n['id'], {'path': str(self.root / 'absent.png'), 'url': 'https://invalid.example/private'})
        bundle = self.store.export_bundle('alice', self.cid, self.root)
        imported = self.store.import_bundle('bob', bundle)
        image = self.store.node('bob', imported)['image']
        self.assertIn('skipped', image['archive_note'])
        self.assertNotIn('path', image)
        self.assertNotIn('url', image)

    def test_expanded_zip_limit_and_missing_parent_rejected(self):
        from unittest.mock import patch
        bundle = self.store.export_bundle('alice', self.cid, self.root)
        with zipfile.ZipFile(bundle) as z:
            data = json.loads(z.read('manifest.json'))
        oversized = self.root / 'huge.zip'
        with zipfile.ZipFile(oversized, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json', json.dumps(data))
            z.writestr('images/big.bin', b'0' * 4096)
        with patch('duhe.storage.MAX_ENTRY', 2048):
            with self.assertRaises(ValueError):
                self.store.import_bundle('bob', oversized)
        data['nodes'].append(dict(data['nodes'][0], id='child', parent_id='missing'))
        bad = self.root / 'orphan.zip'
        with zipfile.ZipFile(bad, 'w') as z:
            z.writestr('manifest.json', json.dumps(data))
        with self.assertRaises(ValueError):
            self.store.import_bundle('bob', bad)

    def test_owner_checks_cover_all_mutations(self):
        n = self.store.node('alice', self.cid)
        operations = [
            lambda: self.store.node('bob', self.cid, n['id']),
            lambda: self.store.nodes('bob', self.cid),
            lambda: self.store.history('bob', self.cid),
            lambda: self.store.select('bob', self.cid, n['id']),
            lambda: self.store.set_image('bob', self.cid, n['id'], {}),
            lambda: self.store.feedback('bob', self.cid, n['id'], {}),
            lambda: self.store.commit('bob', self.cid, n['id'], 0, 'theft', {}, '', {}),
            lambda: self.store.export_bundle('bob', self.cid, self.root),
        ]
        for operation in operations:
            with self.assertRaises(PermissionError):
                operation()
        self.assertEqual(self.store.campaign('alice', self.cid)['revision'], 0)


class ArchiveReviewRegressions(unittest.TestCase):
    def test_manifest_exact_limit_roundtrips_and_one_byte_over_fails_before_zip(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'db.sqlite')
            cid = store.create('alice', new_game())
            n = store.node('alice', cid)
            store.commit('alice', cid, n['id'], 0, 'long', new_game(), '中文' * 1000, {})
            baseline = store.export_bundle('alice', cid, root)
            with zipfile.ZipFile(baseline) as z:
                size = len(z.read('manifest.json'))
            with patch('duhe.storage.MAX_ENTRY', size):
                bundle = store.export_bundle('alice', cid, root)
                restored = store.import_bundle('bob', bundle)
                self.assertEqual(store.node('bob', restored)['text'], '中文' * 1000)
            before = set(root.glob('*.zip'))
            with patch('duhe.storage.MAX_ENTRY', size - 1):
                with self.assertRaisesRegex(ValueError, 'Manifest'):
                    store.export_bundle('alice', cid, root)
            self.assertEqual(set(root.glob('*.zip')), before)

    def test_restored_image_suffix_follows_verified_content_not_source_name(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'db.sqlite')
            for fmt, suffix in [('PNG', '.png'), ('JPEG', '.jpg'), ('WEBP', '.webp')]:
                with self.subTest(format=fmt):
                    cid = store.create('alice', new_game())
                    n = store.node('alice', cid)
                    image = root / 'misleading.svg'
                    Image.new('RGB', (3, 3), 'blue').save(image, format=fmt)
                    content = image.read_bytes()
                    store.set_image('alice', cid, n['id'], {'path': str(image)})
                    bundle = store.export_bundle('alice', cid, root)
                    restored = store.import_bundle('bob', bundle)
                    path = Path(store.node('bob', restored)['image']['path'])
                    self.assertEqual(path.suffix, suffix)
                    self.assertEqual(path.read_bytes(), content)
                    self.assertTrue(path.is_relative_to(store.media_dir))

    def test_invalid_ancestor_is_rejected_even_when_current_state_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'db.sqlite')
            cid = store.create('alice', new_game())
            n = store.node('alice', cid)
            store.commit('alice', cid, n['id'], 0, 'valid-child', new_game(), '', {})
            bundle = store.export_bundle('alice', cid, root)
            with zipfile.ZipFile(bundle) as z:
                manifest = json.loads(z.read('manifest.json'))
            for key in ['completed_operations', 'schema', 'world_version']:
                with self.subTest(field=key):
                    bad = json.loads(json.dumps(manifest))
                    del bad['nodes'][0]['state'][key]
                    corrupted = root / 'corrupted.zip'
                    with zipfile.ZipFile(corrupted, 'w') as z:
                        z.writestr('manifest.json', json.dumps(bad))
                    with self.assertRaises(ValueError):
                        store.import_bundle('bob', corrupted)

class ManualSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'manual.db')
        self.cid = self.store.create('alice', new_game(mode='demo'))
        self.base = self.store.node('alice', self.cid)
        self.original = self.store.commit('alice', self.cid, self.base['id'], 0, 'start',
            new_game(mode='demo'), 'Original story', {'reward': 3}, {'source': 'model', 'model': 'v1'})

    def tearDown(self):
        self.tmp.cleanup()

    def test_fork_text_preserves_state_and_provenance_without_reward_replay(self):
        self.store.set_image('alice', self.cid, self.original['id'], {'path': 'existing.png', 'status': 'SUCCEEDED'})
        fork = self.store.fork_text('alice', self.cid, self.original['id'], 'Edited story')
        self.assertEqual(fork['parent_id'], self.base['id'])
        self.assertEqual(fork['state'], self.original['state'])
        self.assertEqual(fork['event'], {'reward': 3})
        self.assertEqual(fork['meta']['source'], 'human_edit')
        self.assertEqual(fork['meta']['original_source'], 'model')
        self.assertEqual(fork['meta']['original_node'], self.original['id'])
        self.assertEqual(fork['meta']['model'], 'v1')
        self.assertEqual(fork['image'], {'path': 'existing.png', 'status': 'REVIEW_NEEDED'})
        self.assertEqual(self.store.node('alice', self.cid)['id'], fork['id'])
        self.assertEqual(self.store.campaign('alice', self.cid)['revision'], 2)
        self.assertEqual(self.store.node('alice', self.cid, self.original['id'])['text'], 'Original story')
        with self.assertRaises(ValueError):
            self.store.fork_text('alice', self.cid, self.base['id'], 'Root edit')

    def test_text_export_only_contains_selected_branch(self):
        self.store.fork_text('alice', self.cid, self.original['id'], 'Edited story')
        export = self.store.export_text('alice', self.cid, self.root)
        text = export.read_text(encoding='utf-8')
        self.assertEqual(export.suffix, '.md')
        self.assertIn('Edited story', text)
        self.assertIn('demo', text)
        self.assertIn('human_edit', text)
        self.assertNotIn('Original story', text)

    def test_save_slots_persist_restore_and_isolate_owners(self):
        slot = self.store.save_slot('alice', self.cid, '../Label only')
        fork = self.store.fork_text('alice', self.cid, self.original['id'], 'Edited')
        restarted = Store(self.root / 'manual.db')
        rows = restarted.slots('alice')
        self.assertEqual(rows[0]['id'], slot)
        self.assertEqual(rows[0]['label'], '../Label only')
        self.assertEqual(restarted.slots('bob'), [])
        restored = restarted.load_slot('alice', slot)
        self.assertEqual(restored, {'campaign_id': self.cid, 'node_id': self.original['id']})
        self.assertEqual(restarted.node('alice', self.cid)['id'], self.original['id'])
        self.assertEqual(restarted.campaign('alice', self.cid)['revision'], 3)
        self.assertEqual(list(self.root.iterdir()), [self.root / 'manual.db'])
        with self.assertRaises(PermissionError):
            restarted.load_slot('bob', slot)
        for operation in [lambda: restarted.save_slot('bob', self.cid, 'bad'),
                          lambda: restarted.fork_text('bob', self.cid, fork['id'], 'bad'),
                          lambda: restarted.export_text('bob', self.cid, self.root)]:
            with self.assertRaises(PermissionError):
                operation()

    def test_slot_boundaries_and_same_label_overwrite(self):
        first = self.store.save_slot('alice', self.cid, 'x' * 40)
        for i in range(19):
            self.store.save_slot('alice', self.cid, 'slot ' + str(i))
        with self.assertRaises(ValueError):
            self.store.save_slot('alice', self.cid, '21st')
        with self.assertRaises(ValueError):
            self.store.save_slot('alice', self.cid, 'x' * 41)
        self.store.fork_text('alice', self.cid, self.original['id'], 'Edited')
        self.assertEqual(self.store.save_slot('alice', self.cid, 'x' * 40), first)
        self.assertEqual(len(self.store.slots('alice')), 20)
        restored = self.store.load_slot('alice', first)
        self.assertEqual(self.store.node('alice', self.cid)['text'], 'Edited')
