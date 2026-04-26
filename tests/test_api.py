"""
Tests — API Gateway FastAPI.

Vérifie les endpoints REST sans lancer le vrai pipeline LangGraph.
Le pipeline est mocké pour retourner immédiatement un état connu.
"""

import queue
import threading

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api import app, _runs


@pytest.fixture(autouse=True)
def clear_runs():
    """Vider le registre de runs avant chaque test."""
    _runs.clear()
    yield
    _runs.clear()


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "runs_total" in data

    def test_health_compte_runs(self, client):
        _runs["fake-id"] = {"run_id": "fake-id", "status": "done"}
        resp = client.get("/health")
        assert resp.json()["runs_total"] == 1


class TestRecruterEndpoint:
    def test_recruter_fiche_vide_422(self, client):
        resp = client.post("/recruter", json={"fiche_poste": "   "})
        assert resp.status_code == 422

    def test_recruter_lance_run(self, client):
        """Un POST /recruter crée un run et retourne run_id."""
        with patch("src.api._run_pipeline"):
            resp = client.post("/recruter", json={"fiche_poste": "Dev Python senior"})

        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "running"
        assert data["run_id"] in data["message"]

    def test_recruter_enregistre_run(self, client):
        """Après /recruter, le run apparaît dans _runs."""
        with patch("src.api._run_pipeline"):
            resp = client.post("/recruter", json={"fiche_poste": "Data Scientist ML"})

        run_id = resp.json()["run_id"]
        assert run_id in _runs
        assert _runs[run_id]["fiche_poste"] == "Data Scientist ML"


class TestRapportEndpoint:
    def test_rapport_run_inexistant_404(self, client):
        resp = client.get("/rapport/inexistant-uuid")
        assert resp.status_code == 404

    def test_rapport_run_en_cours(self, client):
        run_id = "test-uuid-123"
        _runs[run_id] = {
            "run_id": run_id,
            "status": "running",
            "rapport": None,
            "candidats": None,
            "erreur": None,
            "started_at": "2026-04-15T10:00:00",
            "finished_at": None,
        }
        resp = client.get(f"/rapport/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["rapport"] is None

    def test_rapport_run_termine(self, client):
        run_id = "done-uuid-456"
        _runs[run_id] = {
            "run_id": run_id,
            "status": "done",
            "rapport": "Rapport final : 2 candidats retenus.",
            "candidats": [{"nom": "Alice", "score_final": 85.0}],
            "erreur": None,
            "started_at": "2026-04-15T10:00:00",
            "finished_at": "2026-04-15T10:05:00",
        }
        resp = client.get(f"/rapport/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "done"
        assert "Alice" in data["rapport"] or data["candidats"][0]["nom"] == "Alice"
        assert data["finished_at"] is not None

    def test_rapport_run_erreur(self, client):
        run_id = "err-uuid-789"
        _runs[run_id] = {
            "run_id": run_id,
            "status": "error",
            "rapport": None,
            "candidats": None,
            "erreur": "Connection refused: Ollama not running",
            "started_at": "2026-04-15T10:00:00",
            "finished_at": "2026-04-15T10:00:02",
        }
        resp = client.get(f"/rapport/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert data["erreur"] is not None


class TestListRuns:
    def test_liste_vide(self, client):
        resp = client.get("/runs")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_liste_avec_runs(self, client):
        for i in range(3):
            _runs[f"run-{i}"] = {
                "run_id": f"run-{i}",
                "status": "done",
                "started_at": f"2026-04-15T10:0{i}:00",
                "finished_at": f"2026-04-15T10:0{i}:30",
            }
        resp = client.get("/runs")
        data = resp.json()
        assert data["total"] == 3
        assert len(data["runs"]) == 3


def _minimal_run(run_id: str, status: str = "running") -> dict:
    """Fabrique un run_id fictif avec les champs internes requis par SSE/HITL."""
    return {
        "run_id": run_id,
        "status": status,
        "rapport": None,
        "candidats": None,
        "erreur": None,
        "started_at": "2026-04-15T10:00:00",
        "finished_at": None,
        "_event_queue": queue.Queue(),
        "_hitl_event": threading.Event(),
        "_hitl_decision": {},
        "_candidats_pending_hitl": [],
        "_with_interrupt": True,
    }


class TestStreamEndpoint:
    def test_stream_run_inexistant_404(self, client):
        resp = client.get("/runs/unknown/stream")
        assert resp.status_code == 404

    def test_stream_headers_sse(self, client):
        run_id = "stream-1"
        _runs[run_id] = _minimal_run(run_id)
        # Fermer immédiatement le flux pour que TestClient ne bloque pas.
        _runs[run_id]["_event_queue"].put(None)

        resp = client.get(f"/runs/{run_id}/stream")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert resp.headers["cache-control"] == "no-cache"

    def test_stream_diffuse_evenements_dans_ordre(self, client):
        run_id = "stream-2"
        _runs[run_id] = _minimal_run(run_id)
        q = _runs[run_id]["_event_queue"]
        q.put({"type": "run_started", "data": {"fiche_poste": "Dev"}})
        q.put({"type": "node_completed", "data": {"node": "analyste"}})
        q.put(None)

        resp = client.get(f"/runs/{run_id}/stream")
        body = resp.text
        assert "event: run_started" in body
        assert "event: node_completed" in body
        assert body.index("run_started") < body.index("node_completed")
        assert "event: stream_closed" in body

    def test_stream_sentinel_ferme_proprement(self, client):
        run_id = "stream-3"
        _runs[run_id] = _minimal_run(run_id)
        _runs[run_id]["_event_queue"].put(None)

        resp = client.get(f"/runs/{run_id}/stream")
        # Le corps contient uniquement l'événement de fermeture.
        assert "stream_closed" in resp.text


class TestHitlEndpoint:
    def test_hitl_run_inexistant_404(self, client):
        resp = client.post("/runs/unknown/hitl", json={"action": "approve"})
        assert resp.status_code == 404

    def test_hitl_run_pas_en_attente_409(self, client):
        run_id = "hitl-1"
        _runs[run_id] = _minimal_run(run_id, status="running")
        resp = client.post(f"/runs/{run_id}/hitl", json={"action": "approve"})
        assert resp.status_code == 409

    def test_hitl_action_invalide_422(self, client):
        run_id = "hitl-2"
        _runs[run_id] = _minimal_run(run_id, status="awaiting_hitl")
        resp = client.post(f"/runs/{run_id}/hitl", json={"action": "yolo"})
        assert resp.status_code == 422

    def test_hitl_edit_sans_candidats_422(self, client):
        run_id = "hitl-3"
        _runs[run_id] = _minimal_run(run_id, status="awaiting_hitl")
        resp = client.post(f"/runs/{run_id}/hitl", json={"action": "edit"})
        assert resp.status_code == 422

    def test_hitl_approve_signale_le_worker(self, client):
        run_id = "hitl-4"
        _runs[run_id] = _minimal_run(run_id, status="awaiting_hitl")
        assert not _runs[run_id]["_hitl_event"].is_set()

        resp = client.post(f"/runs/{run_id}/hitl", json={"action": "approve"})

        assert resp.status_code == 200
        assert _runs[run_id]["_hitl_event"].is_set()
        assert _runs[run_id]["_hitl_decision"]["action"] == "approve"

    def test_hitl_skip_enregistre_decision(self, client):
        run_id = "hitl-5"
        _runs[run_id] = _minimal_run(run_id, status="awaiting_hitl")
        resp = client.post(f"/runs/{run_id}/hitl", json={"action": "skip"})
        assert resp.status_code == 200
        assert _runs[run_id]["_hitl_decision"]["action"] == "skip"
        assert _runs[run_id]["_hitl_event"].is_set()

    def test_hitl_edit_enregistre_candidats_retenus(self, client):
        run_id = "hitl-6"
        _runs[run_id] = _minimal_run(run_id, status="awaiting_hitl")
        candidats = [
            {
                "candidat_id": "c1", "nom": "Alice",
                "score_final": 82.0, "statut": "valide", "remarques": "",
            }
        ]
        resp = client.post(
            f"/runs/{run_id}/hitl",
            json={"action": "edit", "candidats_retenus": candidats},
        )
        assert resp.status_code == 200
        assert _runs[run_id]["_hitl_decision"]["action"] == "edit"
        assert _runs[run_id]["_hitl_decision"]["candidats_retenus"] == candidats
