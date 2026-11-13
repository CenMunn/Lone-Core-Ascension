"""SQLite campaign trees with owner isolation and portable offline archives."""
from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import io
import json
import sqlite3
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image, UnidentifiedImageError

MAX_BUNDLE = 100 * 1024 * 1024
MAX_ENTRY = 25 * 1024 * 1024
MAX_NODES = 10000


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _id():
    return uuid.uuid4().hex


def _image_suffix(content):
    # Never trust an archive/source filename to choose a browser MIME type.
    # Unknown legacy blobs remain binary rather than being mislabeled as images.
    try:
        with Image.open(io.BytesIO(content)) as image:
            format_name = image.format
            image.verify()
        return {'PNG': '.png', 'JPEG': '.jpg', 'WEBP': '.webp',
                'GIF': '.gif', 'BMP': '.bmp', 'TIFF': '.tiff',
                'ICO': '.ico', 'AVIF': '.avif'}.get(format_name, '.bin')
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return '.bin'


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.media_dir = self.db_path.parent / (self.db_path.stem + '_media')
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS campaigns(id TEXT PRIMARY KEY, owner TEXT NOT NULL, current_node TEXT, revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, parent_id TEXT, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS nodes_campaign ON nodes(campaign_id);
                CREATE TABLE IF NOT EXISTS operations(campaign_id TEXT, operation_id TEXT, node_id TEXT NOT NULL, PRIMARY KEY(campaign_id,operation_id));
                CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, node_id TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS save_slots(id TEXT PRIMARY KEY, owner TEXT NOT NULL, campaign_id TEXT NOT NULL, node_id TEXT NOT NULL, label TEXT NOT NULL, mode TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(owner,label));
            ''')

    @contextlib.contextmanager
    def _db(self, write=False):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _campaign(self, db, owner, cid):
        row = db.execute('SELECT * FROM campaigns WHERE id=?', (cid,)).fetchone()
        if row is None or row['owner'] != owner:
            raise PermissionError('Campaign unavailable for this owner')
        return dict(row)

    def _node(self, db, cid, nid):
        row = db.execute('SELECT body FROM nodes WHERE id=? AND campaign_id=?', (nid, cid)).fetchone()
        if row is None:
            raise ValueError('Unknown node in campaign')
        return json.loads(row['body'])

    def create(self, owner: str, state: dict) -> str:
        if not isinstance(owner, str) or not owner or not isinstance(state, dict):
            raise ValueError('Owner and state required')
        cid, nid = _id(), _id()
        node = dict(id=nid, parent_id=None, state=state, text='', event={}, meta={}, image=None)
        with self._db(True) as db:
            db.execute('INSERT INTO campaigns VALUES(?,?,?,0)', (cid, owner, nid))
            db.execute('INSERT INTO nodes VALUES(?,?,?,?)', (nid, cid, None, _json(node)))
        return cid

    def campaign(self, owner, cid):
        with self._db() as db:
            return self._campaign(db, owner, cid)

    def node(self, owner, cid, nid=None):
        with self._db() as db:
            c = self._campaign(db, owner, cid)
            return self._node(db, cid, nid or c['current_node'])

    def nodes(self, owner, cid):
        with self._db() as db:
            self._campaign(db, owner, cid)
            return [json.loads(r['body']) for r in db.execute('SELECT body FROM nodes WHERE campaign_id=? ORDER BY rowid', (cid,))]

    def history(self, owner, cid, nid=None):
        with self._db() as db:
            c = self._campaign(db, owner, cid)
            current, seen, path = nid or c['current_node'], set(), []
            while current is not None:
                if current in seen:
                    raise ValueError('Cyclic history')
                seen.add(current)
                n = self._node(db, cid, current)
                path.append(n)
                current = n['parent_id']
            return path[::-1]

    def commit(self, owner, cid, parent_id, revision, operation_id, state, text, event, meta=None):
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 200:
            raise ValueError('Unique operation_id required')
        if not isinstance(state, dict) or not isinstance(event, dict) or not isinstance(text, str):
            raise ValueError('Invalid node payload')
        with self._db(True) as db:
            c = self._campaign(db, owner, cid)
            old = db.execute('SELECT node_id FROM operations WHERE campaign_id=? AND operation_id=?', (cid, operation_id)).fetchone()
            if old:
                previous = self._node(db, cid, old['node_id'])
                if (previous['parent_id'] != parent_id or previous['state'] != state
                        or previous['text'] != text or previous['event'] != event):
                    raise ValueError('操作编号已用于其他分支或不同内容，请刷新后重试')
                return previous
            if c['revision'] != revision or c['current_node'] != parent_id:
                raise ValueError('Stale campaign revision')
            self._node(db, cid, parent_id)
            nid = _id()
            n = dict(id=nid, parent_id=parent_id, state=state, text=text, event=event, meta=meta or {}, image=None)
            db.execute('INSERT INTO nodes VALUES(?,?,?,?)', (nid, cid, parent_id, _json(n)))
            db.execute('INSERT INTO operations VALUES(?,?,?)', (cid, operation_id, nid))
            db.execute('UPDATE campaigns SET current_node=?,revision=revision+1 WHERE id=?', (nid, cid))
            return json.loads(_json(n))

    def select(self, owner, cid, nid):
        with self._db(True) as db:
            self._campaign(db, owner, cid)
            n = self._node(db, cid, nid)
            db.execute('UPDATE campaigns SET current_node=?,revision=revision+1 WHERE id=?', (nid, cid))
            return n

    def fork_text(self, owner, cid, nid, text):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Edited text must not be empty')
        with self._db(True) as db:
            self._campaign(db, owner, cid)
            n = self._node(db, cid, nid)
            if n['parent_id'] is None or not n['text'].strip():
                raise ValueError('Complete a story action before editing its text')
            original_meta = n['meta']
            n['meta'] = dict(original_meta,
                             original_source=original_meta.get('original_source', original_meta.get('source')),
                             source='human_edit', original_node=nid)
            n['id'], n['text'] = _id(), text
            if n.get('image'):
                n['image']['status'] = 'REVIEW_NEEDED'
            db.execute('INSERT INTO nodes VALUES(?,?,?,?)', (n['id'], cid, n['parent_id'], _json(n)))
            db.execute('UPDATE campaigns SET current_node=?,revision=revision+1 WHERE id=?', (n['id'], cid))
            return n

    def export_text(self, owner, cid, output_dir: Path):
        path = self.history(owner, cid)
        mode = path[-1]['state'].get('mode', 'unknown')
        lines = ['# 剧情阅读导出', '', 'Campaign: ' + cid, 'Mode: ' + mode, '']
        for i, node in enumerate(path):
            if not node['text']:
                continue
            lines.extend(['## ' + str(i), '',
                          'Source: ' + str(node['meta'].get('source', 'unknown')), '',
                          node['text'], ''])
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        target = out / ('duhe-reading-' + cid + '-' + _id()[:8] + '.md')
        target.write_text('\n'.join(lines), encoding='utf-8')
        return target

    def save_slot(self, owner, cid, label):
        if not isinstance(label, str) or not label.strip() or len(label) > 40:
            raise ValueError('Save label must contain 1-40 characters')
        label = label.strip()
        with self._db(True) as db:
            c = self._campaign(db, owner, cid)
            n = self._node(db, cid, c['current_node'])
            existing = db.execute('SELECT id FROM save_slots WHERE owner=? AND label=?', (owner, label)).fetchone()
            now = datetime.now(timezone.utc).isoformat()
            if existing:
                slot_id = existing['id']
                db.execute('UPDATE save_slots SET campaign_id=?,node_id=?,mode=?,updated_at=? WHERE id=?',
                           (cid, n['id'], n['state'].get('mode'), now, slot_id))
            else:
                count = db.execute('SELECT COUNT(*) FROM save_slots WHERE owner=?', (owner,)).fetchone()[0]
                if count >= 20:
                    raise ValueError('At most 20 saves; reuse an existing label to overwrite a slot')
                slot_id = _id()
                db.execute('INSERT INTO save_slots VALUES(?,?,?,?,?,?,?,?)',
                           (slot_id, owner, cid, n['id'], label, n['state'].get('mode'), now, now))
            return slot_id

    def slots(self, owner):
        with self._db() as db:
            rows = db.execute('SELECT id,campaign_id,node_id,label,mode,created_at,updated_at FROM save_slots WHERE owner=? ORDER BY updated_at DESC,rowid DESC', (owner,))
            return [dict(row) for row in rows]

    def load_slot(self, owner, slot_id):
        with self._db(True) as db:
            slot = db.execute('SELECT campaign_id,node_id FROM save_slots WHERE id=? AND owner=?', (slot_id, owner)).fetchone()
            if slot is None:
                raise PermissionError('Save slot unavailable for this owner')
            cid, nid = slot['campaign_id'], slot['node_id']
            self._campaign(db, owner, cid)
            self._node(db, cid, nid)
            db.execute('UPDATE campaigns SET current_node=?,revision=revision+1 WHERE id=?', (nid, cid))
            return dict(campaign_id=cid, node_id=nid)

    def set_image(self, owner, cid, nid, image: dict):
        if not isinstance(image, dict):
            raise ValueError('Image metadata required')
        with self._db(True) as db:
            self._campaign(db, owner, cid)
            n = self._node(db, cid, nid)
            n['image'] = image
            db.execute('UPDATE nodes SET body=? WHERE id=?', (_json(n), nid))

    def set_scene(self,owner,cid,nid,scene):
        if not isinstance(scene,dict):raise ValueError('场景记录无效')
        with self._db(True) as db:
            self._campaign(db,owner,cid);n=self._node(db,cid,nid)
            n['meta']['scene']=scene
            db.execute('UPDATE nodes SET body=? WHERE id=?',(_json(n),nid))

    def set_recommendations(self, owner, cid, nid, items):
        with self._db(True) as db:
            self._campaign(db,owner,cid)
            n=self._node(db,cid,nid)
            n['meta']['recommendations']=items
            db.execute('UPDATE nodes SET body=? WHERE id=?',(_json(n),nid))

    def set_tactics_v2(self, owner, cid, nid, items):
        if not isinstance(items, list):
            raise ValueError('战术推荐格式无效')
        with self._db(True) as db:
            self._campaign(db, owner, cid)
            n = self._node(db, cid, nid)
            n['meta']['tactics_v2'] = items
            db.execute('UPDATE nodes SET body=? WHERE id=?', (_json(n), nid))

    def set_suggestions_v2(self, owner, cid, nid, items):
        if not isinstance(items, list):
            raise ValueError('情景推荐格式无效')
        with self._db(True) as db:
            self._campaign(db, owner, cid)
            n = self._node(db, cid, nid)
            n['meta']['suggestions_v2'] = items
            db.execute('UPDATE nodes SET body=? WHERE id=?', (_json(n), nid))

    def feedback(self, owner, cid, nid, data: dict):
        if not isinstance(data, dict):
            raise ValueError('Feedback must be an object')
        with self._db(True) as db:
            self._campaign(db, owner, cid)
            n = self._node(db, cid, nid)
            fid = _id()
            record = dict(data=data, node_meta=n['meta'], state_schema=n['state'].get('schema'), mode=n['state'].get('mode'), created_at=datetime.now(timezone.utc).isoformat())
            db.execute('INSERT INTO feedback VALUES(?,?,?,?)', (fid, cid, nid, _json(record)))
            return fid

    def feedbacks(self, owner, cid, nid=None):
        with self._db() as db:
            self._campaign(db, owner, cid)
            if nid is not None:
                self._node(db, cid, nid)
            sql = 'SELECT id,node_id,body FROM feedback WHERE campaign_id=?'
            args = [cid]
            if nid is not None:
                sql += ' AND node_id=?'
                args.append(nid)
            sql += ' ORDER BY rowid'
            result = []
            for row in db.execute(sql, args):
                body = json.loads(row['body'])
                result.append(dict(id=row['id'], node_id=row['node_id'], data=body['data'],
                                   created_at=body.get('created_at', ''), node_meta=body.get('node_meta', {}),
                                   state_schema=body.get('state_schema'), mode=body.get('mode')))
            return result

    def export_bundle(self, owner, cid, output_dir: Path):
        with self._db() as db:
            c = self._campaign(db, owner, cid)
            nodes = [json.loads(r['body']) for r in db.execute('SELECT body FROM nodes WHERE campaign_id=? ORDER BY rowid', (cid,))]
            feedback = [dict(r) for r in db.execute('SELECT * FROM feedback WHERE campaign_id=?', (cid,))]
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        target = out / ('duhe-' + cid + '-' + _id()[:8] + '.zip')
        payloads = {}
        total = 0
        for n in nodes:
            im = n.get('image')
            if not im:
                continue
            original = im.pop('path', None)
            im.pop('url', None)
            if original and Path(original).is_file():
                p = Path(original)
                if p.stat().st_size > MAX_ENTRY:
                    raise ValueError('Image too large')
                content = p.read_bytes()
                total += len(content)
                if total > MAX_BUNDLE:
                    raise ValueError('Archive too large')
                entry = 'images/' + n['id'] + '.bin'
                payloads[entry] = content
                im['bundle_path'] = entry
            else:
                im['archive_note'] = 'Image unavailable; skipped without network access'
        manifest = _json(dict(schema=1, campaign=c, nodes=nodes, feedback=feedback)).encode('utf-8')
        if len(manifest) > MAX_ENTRY:
            raise ValueError('Manifest exceeds archive entry size limit')
        if len(manifest) + total > MAX_BUNDLE:
            raise ValueError('Archive too large')
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json', manifest)
            for name, content in payloads.items():
                z.writestr(name, content)
        return target

    def import_bundle(self, owner, bundle: Path, *, migrate_v2=False):
        from .rules import validate_state
        from .models_v2 import validate_state_v2

        if Path(bundle).stat().st_size > MAX_BUNDLE:
            raise ValueError('Archive too large')
        try:
            with zipfile.ZipFile(bundle) as z:
                entries = z.infolist()
                names = [i.filename for i in entries]
                if len(entries) > MAX_NODES + 1 or len(set(names)) != len(names):
                    raise ValueError('Invalid archive entries')
                total = 0
                for i in entries:
                    p = PurePosixPath(i.filename)
                    if p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or stat.S_ISLNK(i.external_attr >> 16):
                        raise ValueError('Unsafe archive path')
                    total += i.file_size
                    if i.file_size > MAX_ENTRY or total > MAX_BUNDLE:
                        raise ValueError('Archive exceeds size limit')
                data = json.loads(z.read('manifest.json'))
                nodes = data['nodes']
                c = data['campaign']
                if data.get('schema') != 1 or not isinstance(nodes, list) or not 1 <= len(nodes) <= MAX_NODES:
                    raise ValueError('Unsupported archive')
                graph = {};versions=set()
                for n in nodes:
                    if not isinstance(n, dict) or not isinstance(n.get('id'), str) or n['id'] in graph:
                        raise ValueError('Invalid node id')
                    if not isinstance(n.get('state'), dict) or not isinstance(n.get('text'), str) or not isinstance(n.get('event'), dict) or not isinstance(n.get('meta'), dict):
                        raise ValueError('Invalid node payload')
                    version=n['state'].get('schema');versions.add(version)
                    if version==1:validate_state(n['state'])
                    elif version==2:validate_state_v2(n['state'])
                    else:raise ValueError('Unsupported state version')
                    graph[n['id']] = n
                if len(versions)!=1:raise ValueError('Archive mixes incompatible state versions')
                if c['current_node'] not in graph or sum(n.get('parent_id') is None for n in nodes) != 1:
                    raise ValueError('Invalid campaign graph')
                # Linear-time cycle and connectivity validation, including disconnected cycles.
                done = set()
                for start in graph:
                    seen, current = set(), start
                    while current is not None and current not in done:
                        if current not in graph or current in seen:
                            raise ValueError('Missing parent or cyclic graph')
                        seen.add(current)
                        current = graph[current].get('parent_id')
                    done.update(seen)
                images = {}
                for n in nodes:
                    im = n.get('image')
                    if im is not None and not isinstance(im, dict):
                        raise ValueError('Invalid image')
                    if im:
                        entry = im.get('bundle_path')
                        if entry and (not isinstance(entry, str) or not entry.startswith('images/') or entry not in names):
                            raise ValueError('Missing bundled image')
                        if entry:
                            images[n['id']] = z.read(entry)
                feedback = data.get('feedback', [])
                if not isinstance(feedback, list) or len(feedback) > MAX_NODES:
                    raise ValueError('Invalid feedback')
                for f in feedback:
                    if f['node_id'] not in graph or not isinstance(json.loads(f['body']), dict):
                        raise ValueError('Invalid feedback reference')
        except (KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile, RecursionError) as exc:
            raise ValueError('Invalid archive') from exc
        if versions=={2} and not migrate_v2:
            raise ValueError('这是新版存档，请使用新版游戏载入。')
        if migrate_v2 and versions=={1}:
            from .migrations import migrate_campaign
            converted,converted_ids=migrate_campaign(data)
            images={converted_ids[nid]:content for nid,content in images.items()}
            nodes=converted['nodes'];c=converted['campaign'];feedback=converted.get('feedback',[])
            graph={n['id']:n for n in nodes}
            for node in nodes:validate_state_v2(node['state'])
        cid, mapping = _id(), {nid: _id() for nid in graph}
        written = []
        try:
            for n in nodes:
                old_id = n['id']
                n['id'] = mapping[old_id]
                n['parent_id'] = mapping.get(n.get('parent_id'))
                if n.get('image'):
                    im = n['image']
                    for key in ('path', 'url', 'bundle_path'):
                        im.pop(key, None)
                    if old_id in images:
                        directory = self.media_dir / cid
                        directory.mkdir(parents=True, exist_ok=True)
                        path = directory / (n['id'] + _image_suffix(images[old_id]))
                        path.write_bytes(images[old_id])
                        written.append(path)
                        im['path'] = str(path.resolve())
                    else:
                        im['archive_note'] = 'Image unavailable; skipped without network access'
            with self._db(True) as db:
                db.execute('INSERT INTO campaigns VALUES(?,?,?,0)', (cid, owner, mapping[c['current_node']]))
                for n in nodes:
                    db.execute('INSERT INTO nodes VALUES(?,?,?,?)', (n['id'], cid, n['parent_id'], _json(n)))
                for f in feedback:
                    db.execute('INSERT INTO feedback VALUES(?,?,?,?)', (_id(), cid, mapping[f['node_id']], f['body']))
        except BaseException:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        return cid
