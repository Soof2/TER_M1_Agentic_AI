"""
Layout commun à toutes les pages NiceGUI.

Header, drawer latéral, frame de contenu. À utiliser dans chaque page via
un context manager `with page_frame("titre"): ...` qui applique le layout
et retourne la zone de contenu.
"""

from contextlib import contextmanager

from nicegui import ui

_NAV_ITEMS = [
    ("Accueil", "/", "home"),
    ("Historique des runs", "/runs", "history"),
    ("Mémoire RAG", "/rag", "psychology"),
    ("Métriques", "/metriques", "bar_chart"),
]


@contextmanager
def page_frame(titre: str):
    """Contexte qui instancie le layout et rend la zone de contenu active."""
    ui.colors(primary="#1f6feb")

    with ui.header(elevated=True).classes("items-center justify-between bg-primary text-white"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("hub").classes("text-2xl")
            ui.label("SMA Recrutement").classes("text-lg font-bold")
            ui.label("— Agentic AI (TER M1)").classes("text-sm opacity-70")
        ui.label(titre).classes("text-md opacity-90")

    with ui.left_drawer(value=True, bordered=True).classes("bg-grey-1"):
        ui.label("Navigation").classes("text-xs text-grey-7 uppercase px-3 pt-3")
        for label, path, icon in _NAV_ITEMS:
            with ui.link(target=path).classes(
                "no-underline text-grey-9 hover:text-primary block px-3 py-2"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon(icon)
                    ui.label(label)

    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4") as content:
        yield content


def badge_statut(status: str) -> ui.element:
    """Badge coloré indiquant le statut d'un run."""
    couleurs = {
        "running": "blue",
        "awaiting_hitl": "orange",
        "done": "green",
        "error": "red",
    }
    libelle = {
        "running": "En cours",
        "awaiting_hitl": "Attente validation",
        "done": "Terminé",
        "error": "Erreur",
    }
    return ui.badge(libelle.get(status, status), color=couleurs.get(status, "grey"))
