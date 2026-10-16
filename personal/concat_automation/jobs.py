import fcntl
from contextlib import contextmanager
import sqlite3
import time
from .config import LOCAL


class Jobs:
    def __init__(self):
        LOCAL.mkdir(exist_ok=True)
        self.db = sqlite3.connect(LOCAL / "jobs.sqlite")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL, output TEXT, error TEXT, updated REAL NOT NULL)"
        )
        self.db.commit()

    def find(self, job_id):
        self.db.row_factory = sqlite3.Row
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def update(self, job_id, source, state, stage, output=None, error=None):
        self.db.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state, stage=excluded.stage, output=COALESCE(excluded.output,jobs.output), error=excluded.error, updated=excluded.updated",
            (
                job_id,
                str(source),
                state,
                stage,
                str(output) if output else None,
                error,
                time.time(),
            ),
        )
        self.db.commit()
        print(stage, flush=True)

    def all(self):
        self.db.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in self.db.execute("SELECT * FROM jobs ORDER BY updated DESC")
        ]


@contextmanager
def processing_lock():
    """One pipeline at a time, including manual runs beside the watcher."""
    LOCAL.mkdir(exist_ok=True)
    with (LOCAL / "processing.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                "Já existe um vídeo em processamento. Aguarde a conclusão."
            )
        yield
