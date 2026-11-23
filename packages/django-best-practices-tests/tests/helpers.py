"""Shared helpers: migration control, catalog inspection and concurrent sessions."""

import io
import threading
from contextlib import contextmanager

from django.core.management import call_command
from django.db import connection, connections, transaction


def migrate(app, target):
    call_command('migrate', app, target, verbosity=0)


def sqlmigrate(app, name, backwards=False):
    out = io.StringIO()
    call_command('sqlmigrate', app, name, backwards=backwards, stdout=out)
    return out.getvalue()


def index_names(table):
    with connection.cursor() as cursor:
        cursor.execute('SELECT indexname FROM pg_indexes WHERE tablename = %s', [table])
        return {row[0] for row in cursor.fetchall()}


def relfilenode(table):
    """The table's storage file. It changes when PostgreSQL rewrites the whole table."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT relfilenode FROM pg_class WHERE oid = %s::regclass', [table])
        return cursor.fetchone()[0]


def column_names(table):
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT column_name FROM information_schema.columns WHERE table_name = %s', [table]
        )
        return {row[0] for row in cursor.fetchall()}


def applied_migrations(app):
    from django.db.migrations.recorder import MigrationRecorder

    return set(
        MigrationRecorder(connection).migration_qs.filter(app=app).values_list('name', flat=True)
    )


def foreign_key_oids(table):
    """Map FK constraint name to its oid. A new oid means the constraint was re-created."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT conname, oid FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'f'",
            [table],
        )
        return dict(cursor.fetchall())


class Session:
    """A second database session running in its own thread, as another request would.

    Statements are sent with run() and execute in order on that thread's connection.
    Use it as a context manager; the connection is closed on exit.
    """

    def __init__(self):
        self._jobs = []
        self._cond = threading.Condition()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._closed = False

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def _loop(self):
        conn = connections['default']
        try:
            while True:
                with self._cond:
                    while not self._jobs and not self._closed:
                        self._cond.wait()
                    if not self._jobs and self._closed:
                        return
                    func, done = self._jobs.pop(0)
                try:
                    done['result'] = func(conn)
                except BaseException as error:  # Reported to the caller by wait().
                    done['error'] = error
                done['event'].set()
        finally:
            conn.close()

    def submit(self, func):
        """Queue func(connection) on the session thread; returns a handle for wait()."""
        done = {'event': threading.Event()}
        with self._cond:
            self._jobs.append((func, done))
            self._cond.notify()
        return done

    def run(self, func, timeout=10):
        return self.wait(self.submit(func), timeout)

    @staticmethod
    def wait(done, timeout=10):
        if not done['event'].wait(timeout):
            raise TimeoutError('session did not finish in time')
        if 'error' in done:
            raise done['error']
        return done.get('result')

    @staticmethod
    def is_running(done, grace=0.3):
        """True when the submitted job is still blocked after a short grace period."""
        return not done['event'].wait(grace)

    @contextmanager
    def atomic_hold(self, func):
        """Run func(connection) inside atomic() and keep that transaction open.

        Yields func's return value while the session still holds whatever locks func
        took; the transaction commits when the with block exits.
        """
        started, release, box = threading.Event(), threading.Event(), {}

        def job(conn):
            with transaction.atomic():
                box['value'] = func(conn)
                started.set()
                release.wait(15)

        handle = self.submit(job)
        if not started.wait(10):
            self.wait(handle, timeout=1)  # Re-raises the error func hit.
        try:
            yield box.get('value')
        finally:
            release.set()
            self.wait(handle)

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify()
        self._thread.join(timeout=10)


def execute(sql, params=None):
    """A job for Session.run that executes SQL and returns the rows, if any."""

    def job(conn):
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall() if cursor.description else None

    return job


@contextmanager
def lock_timeout(milliseconds, conn=None):
    """Make the session give up waiting for locks after the given time."""
    conn = conn or connection
    with conn.cursor() as cursor:
        cursor.execute(f'SET lock_timeout = {int(milliseconds)}')
    try:
        yield
    finally:
        with conn.cursor() as cursor:
            cursor.execute('SET lock_timeout = 0')
