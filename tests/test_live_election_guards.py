"""Tests for protecting live-round endpoints from historical election metadata."""
import pytest
from fastapi import HTTPException

import server


def test_live_election_guard_accepts_latest_election_year(monkeypatch):
    monkeypatch.setattr(server, "get_elections", lambda: [
        {"election_id": "AC-2026-AS", "sort_date": "2026", "states": ["S03"]},
        {"election_id": "AC-2025-BR", "sort_date": "2025", "states": ["S04"]},
    ])

    server._require_current_live_election({"election_id": "AC-2026-AS", "sort_date": "2026"})


def test_live_election_guard_rejects_historical_election(monkeypatch):
    monkeypatch.setattr(server, "get_elections", lambda: [
        {"election_id": "AC-2026-AS", "sort_date": "2026", "states": ["S03"]},
        {"election_id": "AC-2025-BR", "sort_date": "2025", "states": ["S04"]},
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


def test_live_election_guard_rejects_current_year_bye_election(monkeypatch):
    monkeypatch.setattr(server, "get_elections", lambda: [
        {"election_id": "AC-2026-AS", "sort_date": "2026", "states": ["S03"]},
        {"election_id": "BYE-2026-10", "sort_date": "2026-10", "states": ["S03"]},
    ])

    with pytest.raises(HTTPException) as exc:
        server._require_current_live_election({"election_id": "BYE-2026-10", "sort_date": "2026-10"})

    assert exc.value.status_code == 400
    assert "by-election" in exc.value.detail


def test_live_election_list_hides_historical_and_bye_metadata(monkeypatch):
    monkeypatch.setattr(server, "get_elections", lambda: [
        {"election_id": "AC-2026-AS", "sort_date": "2026", "states": ["S03"]},
        {"election_id": "AC-2026-TN", "sort_date": "2026", "states": ["S22"]},
        {"election_id": "BYE-2026-10", "sort_date": "2026-10", "states": ["S03"]},
        {"election_id": "AC-2025-BR", "sort_date": "2025", "states": ["S04"]},
        {"election_id": "AC-2026-AS-ARCHIVE", "sort_date": "2026", "states": ["AS"]},
    ])

    elections = server._current_live_elections()

    assert [item["election_id"] for item in elections] == ["AC-2026-TN", "AC-2026-AS"]
