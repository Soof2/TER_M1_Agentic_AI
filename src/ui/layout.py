"""Layout commun à toutes les pages NiceGUI."""

from contextlib import contextmanager
from nicegui import ui

_NAV_ITEMS = [
    ("Accueil", "/", "home"),
    ("Historique", "/runs", "history"),
    ("RAG", "/rag", "psychology"),
    ("Métriques", "/metriques", "bar_chart"),
]


def _score_color(score: float) -> str:
    if score >= 75:
        return "positive"
    if score >= 50:
        return "warning"
    return "negative"


def _score_chip(score: float) -> None:
    color = _score_color(score)
    ui.badge(f"{score:.0f}", color=color).props("rounded")


@contextmanager
def page_frame(titre: str):
    ui.colors(primary="#355e3b", secondary="#c58742", accent="#5f7f52")
    ui.add_head_html("""
    <style>
    body {
      background: linear-gradient(135deg, #f7f1df 0%, #e8ead4 48%, #dce5cf 100%);
      font-family: "Segoe UI", sans-serif;
    }
    .glass-card {
      background: rgba(255,252,241,0.88);
      border: 1px solid rgba(42,64,43,0.15);
      border-radius: 20px;
      box-shadow: 0 8px 32px rgba(34,54,35,0.10);
    }
    .nav-link { border-radius: 10px; transition: background 0.15s; }
    .nav-link:hover { background: rgba(53,94,59,0.10); }
    a { color: #355e3b; }
    </style>
    """)

    with ui.header(elevated=True).classes("items-center justify-between px-4 py-2").style(
        "background: #355e3b; color: white;"
    ):
        with ui.row().classes("items-center gap-4"):
            with ui.row().classes("items-center gap-2 mr-2"):
                ui.icon("hub").classes("text-2xl")
                ui.label("SMA Recrutement").classes("text-base font-bold")
            for label, path, icon in _NAV_ITEMS:
                ui.button(label, icon=icon,
                          on_click=lambda p=path: ui.navigate.to(p)).props(
                    "flat color=white no-caps"
                ).classes("text-sm")
        ui.label(titre).classes("text-sm opacity-70")

    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4") as content:
        yield content


def badge_statut(status: str) -> ui.element:
    couleurs = {
        "running": "blue",
        "awaiting_hitl": "orange",
        "done": "green",
        "error": "red",
    }
    libelle = {
        "running": "En cours",
        "awaiting_hitl": "En attente HITL",
        "done": "Terminé",
        "error": "Erreur",
    }
    return ui.badge(libelle.get(status, status), color=couleurs.get(status, "grey"))
