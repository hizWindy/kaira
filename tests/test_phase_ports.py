"""Tests for automatic port resolution and dev-server discovery.

Covers:
- The probe: what counts as taken, and what counts as inconclusive.
- The scan: where it starts, that it moves, and that it is bounded.
- Strict mode: the one caller that wants a failure instead of a shift.
- The runtime record: written, read back, and distrusted once stale.
- ``kaira run``: the resolved port reaching the command line and the banner.
"""

from __future__ import annotations

import json
import socket

import pytest
from typer.testing import CliRunner

from kaira.core import ports

runner = CliRunner()


@pytest.fixture()
def bound_port():
    """Hold a real listening socket and yield the port it occupies."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        yield srv.getsockname()[1]
    finally:
        srv.close()


def _taken(*busy: int):
    """Return a probe reporting every port in *busy* as unavailable."""

    def probe(_host: str, port: int) -> bool:
        return port not in busy

    return probe


# ---------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------


class TestProbe:
    def test_a_listening_socket_makes_its_port_unavailable(self, bound_port):
        assert ports.is_port_free("127.0.0.1", bound_port) is False

    def test_a_port_nobody_holds_is_available(self, bound_port):
        # The fixture's port is free again the moment the socket closes, so a
        # port from the same ephemeral range that nothing bound stands in.
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
        probe.close()
        assert ports.is_port_free("127.0.0.1", free) is True

    def test_an_unresolvable_host_is_inconclusive_not_taken(self):
        """A bad host is not a port problem, and shifting would not fix it."""
        assert ports.is_port_free("no-such-host.invalid", 8000) is True

    def test_the_probe_binds_rather_than_connects(self):
        """A socket bound but never listening still blocks a bind.

        This is the case a connect-probe gets wrong: nothing is accepting, so
        connecting fails and the port looks free, but binding still cannot.
        """
        held = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        held.bind(("127.0.0.1", 0))  # deliberately no listen()
        port = held.getsockname()[1]
        try:
            assert ports.is_port_free("127.0.0.1", port) is False
        finally:
            held.close()


# ---------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------


class TestResolvePort:
    def test_a_free_port_is_left_alone(self):
        res = ports.resolve_port("127.0.0.1", 8000, probe=_taken())
        assert res.port == 8000
        assert res.shifted is False
        assert res.scanned == 1

    def test_a_taken_port_moves_to_the_next_free_one(self):
        res = ports.resolve_port("127.0.0.1", 8000, probe=_taken(8000))
        assert res.port == 8001
        assert res.requested == 8000
        assert res.shifted is True

    def test_the_scan_walks_past_a_run_of_taken_ports(self):
        res = ports.resolve_port(
            "127.0.0.1", 8000, probe=_taken(8000, 8001, 8002, 8003)
        )
        assert res.port == 8004
        assert res.scanned == 5

    def test_the_scan_is_bounded(self):
        """Twenty taken ports is a machine problem, not one a 21st port fixes."""
        with pytest.raises(ports.PortUnavailableError):
            ports.resolve_port(
                "127.0.0.1", 8000, limit=5, probe=_taken(*range(8000, 8005))
            )

    def test_the_scan_never_walks_past_the_last_port(self):
        with pytest.raises(ports.PortUnavailableError):
            ports.resolve_port(
                "127.0.0.1",
                ports.MAX_PORT - 1,
                probe=_taken(ports.MAX_PORT - 1, ports.MAX_PORT),
            )

    def test_the_default_is_the_fastapi_default(self):
        assert ports.DEFAULT_PORT == 8000

    def test_a_real_taken_port_shifts_without_a_stub(self, bound_port):
        """End to end against a live socket, with no injected probe."""
        res = ports.resolve_port("127.0.0.1", bound_port)
        assert res.port != bound_port
        assert res.shifted is True


class TestStrictMode:
    def test_strict_refuses_to_move(self):
        with pytest.raises(ports.PortUnavailableError) as exc:
            ports.resolve_port("127.0.0.1", 8000, strict=True, probe=_taken(8000))
        assert "8000" in str(exc.value)

    def test_strict_is_satisfied_by_a_free_port(self):
        res = ports.resolve_port("127.0.0.1", 8000, strict=True, probe=_taken())
        assert res.port == 8000 and res.shifted is False


# ---------------------------------------------------------------------------
# The runtime record
# ---------------------------------------------------------------------------


class TestRuntimeRecord:
    def test_a_recorded_server_is_read_back(self, tmp_path, bound_port):
        ports.record_server("127.0.0.1", bound_port, tmp_path)
        assert ports.read_server(tmp_path) == ("127.0.0.1", bound_port)

    def test_a_stale_record_is_not_trusted(self, tmp_path):
        """A crashed server leaves its file behind; nothing holds the port."""
        free = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()

        ports.record_server("127.0.0.1", port, tmp_path)
        assert ports.read_server(tmp_path) is None

    def test_a_missing_record_reads_as_nothing(self, tmp_path):
        assert ports.read_server(tmp_path) is None

    def test_a_corrupt_record_reads_as_nothing(self, tmp_path):
        path = ports.runtime_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert ports.read_server(tmp_path) is None

    def test_clearing_removes_the_record(self, tmp_path, bound_port):
        ports.record_server("127.0.0.1", bound_port, tmp_path)
        ports.clear_server(tmp_path)
        assert not ports.runtime_path(tmp_path).exists()

    def test_clearing_a_record_that_is_not_there_is_not_an_error(self, tmp_path):
        ports.clear_server(tmp_path)  # must not raise

    def test_another_process_record_is_left_alone(self, tmp_path, bound_port):
        """A second server in one project overwrites the record; its exit must
        not delete what now belongs to the first."""
        import json as _json
        import os as _os

        ports.record_server("127.0.0.1", bound_port, tmp_path)
        path = ports.runtime_path(tmp_path)
        data = _json.loads(path.read_text(encoding="utf-8"))
        data["pid"] = _os.getpid() + 1
        path.write_text(_json.dumps(data), encoding="utf-8")

        ports.clear_server(tmp_path)
        assert path.exists()

    def test_an_unreadable_record_is_removed_anyway(self, tmp_path):
        path = ports.runtime_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        ports.clear_server(tmp_path)
        assert not path.exists()

    def test_recording_creates_the_kaira_directory(self, tmp_path, bound_port):
        ports.record_server("127.0.0.1", bound_port, tmp_path)
        data = json.loads(ports.runtime_path(tmp_path).read_text(encoding="utf-8"))
        assert data["port"] == bound_port and "pid" in data


class TestBaseUrl:
    def test_without_a_record_the_default_stands(self, tmp_path):
        assert ports.resolve_base_url(tmp_path) == "http://127.0.0.1:8000"

    def test_a_live_record_wins_over_the_default(self, tmp_path, bound_port):
        ports.record_server("127.0.0.1", bound_port, tmp_path)
        assert ports.resolve_base_url(tmp_path) == f"http://127.0.0.1:{bound_port}"

    def test_a_wildcard_bind_is_reported_as_loopback(self, tmp_path, monkeypatch):
        """Nothing can be reached *at* 0.0.0.0 — a client needs an address.

        The record is stubbed rather than written, because what is under test
        is how a wildcard host is turned into a URL, not whether the port is
        still held.
        """
        monkeypatch.setattr(ports, "read_server", lambda root=None: ("0.0.0.0", 8123))
        assert ports.resolve_base_url(tmp_path) == "http://127.0.0.1:8123"


# ---------------------------------------------------------------------------
# kaira run
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_kaira_run_invokes_kaira_app(self, monkeypatch):
        """kaira run uses KairaApp instead of subprocess."""
        captured = {}

        def fake_run(self, dev, host, port, **kwargs):
            captured["dev"] = dev
            captured["host"] = host
            captured["port"] = port

        monkeypatch.setattr("kaira.app.KairaApp.run", fake_run)

        from kaira.commands import run_cmd

        result = runner.invoke(run_cmd.app, [])
        assert result.exit_code == 0
        assert "port" in captured
        assert "host" in captured

    def test_kaira_run_passes_prod_flag(self, monkeypatch):
        """kaira run --prod passes prod=False to KairaApp."""
        captured = {}

        def fake_run(self, dev, host, port, **kwargs):
            captured["dev"] = dev

        monkeypatch.setattr("kaira.app.KairaApp.run", fake_run)

        from kaira.commands import run_cmd

        result = runner.invoke(run_cmd.app, ["--prod"])
        assert result.exit_code == 0
        assert captured["dev"] is False
