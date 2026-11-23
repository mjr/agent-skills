"""ops- rules."""

import socket
import threading
import time
import urllib.request

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import InternalError, OperationalError, close_old_connections, connection
from django.db.backends.postgresql.base import DatabaseWrapper

pytestmark = [pytest.mark.django_db(transaction=True)]


def wrapper(**overrides):
    settings_dict = {**connection.settings_dict, **overrides}
    return DatabaseWrapper(settings_dict, alias='default')


# ops-statement-timeout


@pytest.mark.rule('ops-statement-timeout')
def test_statement_timeout_from_connection_options_cancels_slow_queries():
    conn = wrapper(OPTIONS={'options': '-c statement_timeout=200'})
    try:
        with pytest.raises(OperationalError, match='statement timeout'):
            with conn.cursor() as cursor:
                cursor.execute('SELECT pg_sleep(2)')
    finally:
        conn.close()


@pytest.mark.rule('ops-statement-timeout')
def test_set_local_raises_the_limit_for_one_transaction():
    conn = wrapper(OPTIONS={'options': '-c statement_timeout=200'})
    try:
        with conn.cursor() as cursor:
            cursor.execute('BEGIN')
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            cursor.execute('SELECT pg_sleep(0.4)')  # Would be cancelled at 200 ms.
            cursor.execute('COMMIT')
            cursor.execute('SHOW statement_timeout')
            assert cursor.fetchone()[0] == '200ms'  # Back to the connection default.
    finally:
        conn.close()


@pytest.mark.rule('ops-statement-timeout')
def test_idle_in_transaction_timeout_ends_abandoned_transactions():
    conn = wrapper(OPTIONS={'options': '-c idle_in_transaction_session_timeout=200'})
    try:
        with conn.cursor() as cursor:
            cursor.execute('BEGIN')
            cursor.execute('SELECT 1')
        time.sleep(0.6)  # The application "forgets" the open transaction.
        # PostgreSQL closes the session; Django reports it as InternalError.
        with pytest.raises(InternalError, match='idle-in-transaction timeout'):
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1')
    finally:
        conn.close()


# ops-outbound-timeouts


@pytest.fixture
def silent_server():
    """Accepts connections and never answers, like an overloaded partner API."""
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen()
    accepted = []
    stop = threading.Event()

    def serve():
        server.settimeout(0.1)
        while not stop.is_set():
            try:
                accepted.append(server.accept()[0])
            except TimeoutError:
                pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.getsockname()[1]}/'
    stop.set()
    thread.join()
    for conn in accepted:
        conn.close()
    server.close()


@pytest.mark.rule('ops-outbound-timeouts')
def test_python_sockets_have_no_default_timeout():
    assert socket.getdefaulttimeout() is None


@pytest.mark.rule('ops-outbound-timeouts')
def test_a_call_without_timeout_waits_indefinitely(silent_server):
    done = threading.Event()

    def call():
        try:
            urllib.request.urlopen(silent_server)
        except Exception:
            pass
        done.set()

    threading.Thread(target=call, daemon=True).start()
    assert not done.wait(1.5), 'still waiting: a worker would be stuck here'


@pytest.mark.rule('ops-outbound-timeouts')
def test_a_timeout_bounds_the_wait(silent_server):
    started = time.perf_counter()
    with pytest.raises(TimeoutError):
        urllib.request.urlopen(silent_server, timeout=0.3)
    assert time.perf_counter() - started < 1.5


# ops-persistent-connections


def backend_pid(conn):
    with conn.cursor() as cursor:
        cursor.execute('SELECT pg_backend_pid()')
        return cursor.fetchone()[0]


def simulate_requests(conn_max_age):
    """What Django does around every request: close_old_connections() at start and end."""
    original = connection.settings_dict['CONN_MAX_AGE']
    connection.settings_dict['CONN_MAX_AGE'] = conn_max_age
    connection.close()
    pids = []
    try:
        for _ in range(3):
            close_old_connections()
            pids.append(backend_pid(connection))
            close_old_connections()
    finally:
        connection.settings_dict['CONN_MAX_AGE'] = original
        connection.close()
    return pids


@pytest.mark.rule('ops-persistent-connections')
def test_default_opens_a_new_connection_for_every_request():
    pids = simulate_requests(0)
    assert len(set(pids)) == 3


@pytest.mark.rule('ops-persistent-connections')
def test_conn_max_age_reuses_the_connection():
    pids = simulate_requests(60)
    assert len(set(pids)) == 1


@pytest.mark.rule('ops-persistent-connections')
def test_native_pool_is_available_and_excludes_conn_max_age():
    pooled = wrapper(OPTIONS={'pool': True}, CONN_MAX_AGE=0)
    try:
        assert backend_pid(pooled)
        assert pooled.pool is not None
    finally:
        pooled.close_pool()

    with pytest.raises(ImproperlyConfigured):
        wrapper(OPTIONS={'pool': True}, CONN_MAX_AGE=60).pool
