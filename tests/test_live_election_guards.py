"""Tests for protecting live-round endpoints from historical election metadata."""
import pytest
from fastapi import HTTPException

import server


def test_live_election_guard_accepts_latest_election_year(monkeypatch):
    monkeypatch.setattr(server, "get_elections", lambda: [
        {"election_id": "AC-2026-AS", "sort_date": "2026"},
        {"election_id": "AC-2025-BR", "sort_date": "2025"},
    ])

    server._require_current_live_election({"election_id": "AC-2026-AS", "sort_date": "2026"})


def test_live_election_guard_rejects_historical_election(monkeypatch):
    monkeypatch.setattr(server, "get_elections", lambda: [
        {"election_id": "AC-2026-AS", "sort_date": "2026"},
        {"election_id": "AC-2025-BR", "sort_date": "2025"},
    ])

    with pytest.raises(HTTPException) as exc:
        server._require_current_live_election({"election_id": "AC-2025-BR", "sort_date": "2025"})

    assert exc.value.status_code == 400
    assert "/api/archive/results" in exc.value.detail


def test_live_election_guard_rejects_when_metadata_empty(monkeypatch):
    monkeypatch.setattr(server, "get_elections", lambda: [])

    with pytest.raises(HTTPException) as exc:
        server._require_current_live_election({"election_id": "AC-2026-AS", "sort_date": "2026"})

    assert exc.value.status_code == 400
