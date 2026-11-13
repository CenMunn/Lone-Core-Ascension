"""持久化调用计数；默认无上限，可显式传入有限预算用于测试。"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Budget:
    def __init__(self, path: Path, limits=None):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.limits={'text':None,'image':None} if limits is None else limits
        with self._connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, kind TEXT, purpose TEXT, at TEXT)')
    @contextmanager
    def _connect(self):
        c=sqlite3.connect(self.path,timeout=20)
        try:
            with c: yield c
        finally:
            c.close()
    def charge(self, kind, purpose):
        if kind not in self.limits: raise ValueError('未知额度类型')
        with self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            used=c.execute('SELECT count(*) FROM attempts WHERE kind=?',(kind,)).fetchone()[0]
            if self.limits[kind] is not None and used>=self.limits[kind]: raise RuntimeError(f'{kind}真实联调额度已用完，请先确认新的调用额度。')
            c.execute('INSERT INTO attempts(kind,purpose,at) VALUES(?,?,?)',(kind,str(purpose)[:200],datetime.now(timezone.utc).isoformat()))
    def ensure_available(self, *, text=0, image=0):
        status=self.status()
        for kind,needed in (('text',text),('image',image)):
            if status[kind]['limit'] is None:continue
            remaining=status[kind]['limit']-status[kind]['used']
            if remaining<needed:
                label='文本' if kind=='text' else '图片'
                raise RuntimeError(f'{label}调用额度不足：本次需要{needed}次，剩余{remaining}次（已用{status[kind]["used"]}/{status[kind]["limit"]}）。请关闭自动配图以减少用量，或选择本地规则演示；新增真实额度需先确认。')
    def status(self):
        with self._connect() as c:
            return {k:{'used':c.execute('SELECT count(*) FROM attempts WHERE kind=?',(k,)).fetchone()[0],'limit':v} for k,v in self.limits.items()}
