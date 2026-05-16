"""
Interface graphique NiceGUI pour le SMA de recrutement.

L'UI reste volontairement cliente de l'API FastAPI : elle lance les runs via
REST, suit l'exécution via SSE et soumet les décisions HITL sans importer le
graphe LangGraph.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

import httpx
from nicegui import background_tasks, ui

from src.ui.api_client import (
    API_URL,
    get_metrics_summary,
    get_rag_summary,
    get_rapport,
    health,
    launch_run,
    list_runs,
    search_rag,
    stream_events,
    submit_hitl,
)
from src.ui.layout import badge_statut, page_frame


NODE_LABELS = {
    "orchestrateur": "A1 Orchestrateur",
    "analyste": "A2 Analyste",
    "chercheur_stratege": "A3a Stratege",
    "chercheur_collecteur": "A3b Collecteur",
    "chercheur_filtre": "A3c Filtre",
    "deduplicateur": "A6 Deduplicateur",
    "evaluateur": "A4 Evaluateur",
    "reduce_scores": "Reduce",
    "verificateur": "A5 Verificateur",
    "recruteur": "A7 Recruteur",
    "rapport": "Rapport",
    "persistance": "A8 RAG",
}

PIPELINE_ORDER = [
    "orchestrateur",
    "analyste",
    "chercheur_stratege",
    "chercheur_collecteur",
    "chercheur_filtre",
    "deduplicateur",
    "evaluateur",
    "reduce_scores",
    "verificateur",
    "recruteur",
    "rapport",
    "persistance",
]


def _install_theme() -> None:
    ui.add_head_html(
        """
        <style>
        :root {
          --ink: #172018;
          --moss: #355e3b;
          --leaf: #5f7f52;
          --sand: #f4ecd8;
          --paper: rgba(255, 252, 241, 0.86);
          --line: rgba(42, 64, 43, 0.16);
        }
        body {
          color: var(--ink);
          background:
            radial-gradient(circle at 14% 10%, rgba(95, 127, 82, 0.26), transparent 30%),
            radial-gradient(circle at 88% 18%, rgba(197, 135, 66, 0.20), transparent 28%),
            linear-gradient(135deg, #f7f1df 0%, #e8ead4 48%, #dce5cf 100%);
          font-family: "Aptos", "Segoe UI", sans-serif;
        }
        .glass-card {
          background: var(--paper);
          border: 1px solid var(--line);
          border-radius: 24px;
          box-shadow: 0 22px 70px rgba(34, 54, 35, 0.12);
          backdrop-filter: blur(14px);
        }
        .section-title {
          letter-spacing: -0.04em;
          line-height: 0.95;
        }
        .timeline-item {
          border-left: 4px solid var(--leaf);
          background: rgba(255, 255, 255, 0.72);
        }
        .metric-card {
          background: linear-gradient(145deg, rgba(255,255,255,.76), rgba(231,239,219,.86));
          border: 1px solid var(--line);
          border-radius: 20px;
        }
        .report-markdown table {
          display: block;
          width: 100%;
          overflow-x: auto;
          border-collapse: collapse;
          font-size: 0.92rem;
        }
        .report-markdown th,
        .report-markdown td {
          border: 1px solid rgba(42, 64, 43, 0.16);
          padding: 8px 10px;
          vertical-align: top;
        }
        .report-markdown th {
          background: rgba(53, 94, 59, 0.10);
          color: var(--ink);
        }
        .report-markdown pre {
          white-space: pre-wrap;
          border-radius: 12px;
        }
        </style>
        """
    )
    ui.colors(primary="#355e3b", secondary="#c58742", accent="#5f7f52")


def _format_date(value: str | None) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return value


def _candidate_rows(candidats: list[dict] | None) -> list[dict]:
    rows = []
    for c in candidats or []:
        rows.append({
            "nom": c.get("nom", "?"),
            "score_final": c.get("score_final", c.get("score", "")),
            "statut": c.get("statut", ""),
            "source": c.get("source", ""),
            "remarques": c.get("remarques", "")[:160],
        })
    return rows


def _candidate_columns() -> list[dict]:
    return [
        {"name": "nom", "label": "Candidat", "field": "nom", "align": "left"},
        {"name": "score_final", "label": "Score", "field": "score_final", "align": "left"},
        {"name": "statut", "label": "Statut", "field": "statut", "align": "left"},
        {"name": "source", "label": "Source", "field": "source", "align": "left"},
        {"name": "remarques", "label": "Remarques", "field": "remarques", "align": "left"},
    ]


def _candidate_stats(candidats: list[dict] | None) -> dict[str, int]:
    stats = {"valide": 0, "douteux": 0, "invalide": 0}
    for candidat in candidats or []:
        statut = str(candidat.get("statut", "")).lower()
        if statut in stats:
            stats[statut] += 1
    stats["total"] = sum(stats.values())
    return stats


def _scores_stats(candidats: list[dict] | None) -> dict[str, float]:
    scores = []
    for candidat in candidats or []:
        try:
            scores.append(float(candidat.get("score_final", candidat.get("score", 0)) or 0))
        except (TypeError, ValueError):
            continue
    if not scores:
        return {"max": 0.0, "moyenne": 0.0}
    return {"max": max(scores), "moyenne": round(sum(scores) / len(scores), 1)}


def _status_chart_options(stats: dict[str, int]) -> dict:
    data = [
        {"value": stats.get("valide", 0), "name": "Valides", "itemStyle": {"color": "#2f855a"}},
        {"value": stats.get("douteux", 0), "name": "Douteux", "itemStyle": {"color": "#c58742"}},
        {"value": stats.get("invalide", 0), "name": "Invalides", "itemStyle": {"color": "#c2410c"}},
    ]
    if not any(item["value"] for item in data):
        data = [{"value": 1, "name": "Aucun candidat", "itemStyle": {"color": "#9ca3af"}}]
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"bottom": 0, "left": "center"},
        "series": [{
            "name": "Statuts",
            "type": "pie",
            "radius": ["44%", "72%"],
            "center": ["50%", "42%"],
            "avoidLabelOverlap": True,
            "label": {"formatter": "{b}\n{c}", "fontSize": 12},
            "data": data,
        }],
    }


def _extract_report_section(markdown: str, title: str) -> str:
    """Extrait le contenu d'une section Markdown de niveau 2."""
    if not markdown:
        return ""
    pattern = rf"^## {re.escape(title)}\s*$"
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_section = re.search(r"^##\s+", markdown[start:], flags=re.MULTILINE)
    end = start + next_section.start() if next_section else len(markdown)
    return markdown[start:end].strip()


def _strip_text_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:text)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_execution_metrics(markdown: str) -> dict[str, Any]:
    """Transforme la section métriques du rapport en données affichables."""
    section = _strip_text_fence(_extract_report_section(markdown, "Métriques d'exécution"))
    run_match = re.search(r"Run ID\s*:\s*(.+)", section)
    duration_match = re.search(r"Durée totale\s*:\s*([\d.]+)s", section)

    steps: list[dict[str, Any]] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("Run ID", "Durée totale", "Détail par étape")):
            continue
        match = re.match(r"^(?P<etape>\S+)\s+(?P<duree>[\d.]+|n/a)s\s*(?P<details>.*)$", line)
        if not match:
            continue
        duree_raw = match.group("duree")
        duree = None if duree_raw == "n/a" else float(duree_raw)
        steps.append({
            "etape": match.group("etape"),
            "duree_s": duree,
            "duree_label": "n/a" if duree is None else f"{duree:.2f}s",
            "details": match.group("details").strip() or "-",
        })

    slowest = max((s for s in steps if s["duree_s"] is not None), key=lambda s: s["duree_s"], default=None)
    return {
        "run_id": run_match.group(1).strip() if run_match else "-",
        "duree_totale_s": float(duration_match.group(1)) if duration_match else 0.0,
        "steps": steps,
        "slowest": slowest,
        "raw": section,
    }


def _metrics_chart_options(metrics: dict[str, Any]) -> dict:
    steps = [s for s in metrics.get("steps", []) if s.get("duree_s") is not None]
    top_steps = sorted(steps, key=lambda s: s["duree_s"], reverse=True)[:10]
    top_steps.reverse()
    if not top_steps:
        return {}
    return {
        "grid": {"left": 130, "right": 30, "top": 20, "bottom": 30},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {"type": "value", "name": "secondes"},
        "yAxis": {"type": "category", "data": [s["etape"] for s in top_steps]},
        "series": [{
            "type": "bar",
            "data": [s["duree_s"] for s in top_steps],
            "itemStyle": {"color": "#355e3b"},
            "label": {"show": True, "position": "right", "formatter": "{c}s"},
        }],
    }


def _build_mermaid(completed: set[str], awaiting_hitl: bool = False) -> str:
    lines = [
        "flowchart LR",
        "  orchestrateur[A1 Orchestrateur] --> analyste[A2 Analyste]",
        "  analyste --> chercheur_stratege[A3a Stratege]",
        "  chercheur_stratege --> chercheur_collecteur[A3b Collecteur]",
        "  chercheur_collecteur --> chercheur_filtre[A3c Filtre]",
        "  chercheur_filtre --> deduplicateur[A6 Deduplicateur]",
        "  deduplicateur --> evaluateur[A4 Evaluateur x N]",
        "  evaluateur --> reduce_scores[Reduce]",
        "  reduce_scores --> verificateur[A5 Verificateur]",
        "  verificateur --> recruteur[A7 Recruteur]",
        "  verificateur --> rapport[Rapport]",
        "  recruteur --> rapport",
        "  rapport --> persistance[A8 RAG]",
        "  classDef pending fill:#fffaf0,stroke:#b7a77a,color:#172018;",
        "  classDef done fill:#dcefd5,stroke:#355e3b,color:#172018;",
        "  classDef wait fill:#ffe1b8,stroke:#c58742,color:#172018;",
    ]
    for node in PIPELINE_ORDER:
        lines.append(f"  class {node} {'done' if node in completed else 'pending'};")
    if awaiting_hitl:
        lines.append("  class recruteur wait;")
    return "\n".join(lines)


def _event_title(event_type: str, data: dict[str, Any]) -> str:
    if event_type == "node_completed":
        return f"{NODE_LABELS.get(data.get('node'), data.get('node', 'Noeud'))} termine"
    labels = {
        "run_started": "Run demarre",
        "awaiting_hitl": "Validation humaine requise",
        "hitl_decision": "Decision HITL recue",
        "run_done": "Run termine",
        "run_error": "Erreur pipeline",
        "stream_closed": "Flux ferme",
        "connection_error": "Erreur de connexion SSE",
    }
    return labels.get(event_type, event_type)


@ui.page("/")
async def home_page() -> None:
    _install_theme()
    with page_frame("Accueil"):
        with ui.card().classes("glass-card w-full p-8 gap-5"):
            ui.label("Piloter un recrutement multi-agents").classes(
                "section-title text-5xl font-black text-primary"
            )
            ui.label(
                "Lancez un run LangGraph, suivez les agents en direct et validez le contact candidat avant A7."
            ).classes("text-lg text-grey-8")

            api_status = ui.label("API: verification...").classes("text-sm text-grey-7")
            try:
                status = await health()
                api_status.text = (
                    f"API connectee ({API_URL}) - {status.get('runs_running', 0)} run(s) actif(s)"
                )
            except Exception as exc:  # noqa: BLE001
                api_status.text = f"API indisponible ({API_URL}) : {exc}"
                api_status.classes(add="text-negative")

            fiche = ui.textarea(
                label="Fiche de poste",
                placeholder="Ex: Developpeur Python senior, 5 ans, Paris, FastAPI, LangChain, Docker...",
            ).props("outlined autogrow").classes("w-full")
            fiche.value = (
                "Developpeur Python senior, 5 ans d'experience, Paris ou remote, "
                "FastAPI, LangGraph, Docker, RAG, bonne communication."
            )
            hitl = ui.checkbox(
                "Activer la validation humaine avant le contact candidat (HITL)",
                value=True,
            )

            async def start_run() -> None:
                if not fiche.value or not fiche.value.strip():
                    ui.notify("La fiche de poste est vide.", type="warning")
                    return
                try:
                    result = await launch_run(fiche.value.strip(), no_interrupt=not hitl.value)
                except httpx.HTTPError as exc:
                    ui.notify(f"Erreur API: {exc}", type="negative")
                    return
                ui.navigate.to(f"/runs/{result['run_id']}")

            ui.button("Lancer le pipeline", icon="rocket_launch", on_click=start_run).props(
                "unelevated size=lg"
            ).classes("self-start")


@ui.page("/runs")
async def runs_page() -> None:
    _install_theme()
    with page_frame("Historique"):
        ui.label("Runs de recrutement").classes("section-title text-4xl font-black text-primary")
        container = ui.column().classes("w-full gap-3")

        async def refresh() -> None:
            container.clear()
            try:
                runs = await list_runs()
            except Exception as exc:  # noqa: BLE001
                with container:
                    ui.label(f"Impossible de charger les runs : {exc}").classes("text-negative")
                return

            with container:
                if not runs:
                    ui.label("Aucun run en memoire API pour le moment.").classes("text-grey-7")
                    return
                for run in runs:
                    with ui.card().classes("glass-card w-full p-4"):
                        with ui.row().classes("items-center justify-between w-full gap-3"):
                            with ui.column().classes("gap-1"):
                                ui.label(run["run_id"]).classes("font-mono text-sm")
                                ui.label(f"Debut : {_format_date(run.get('started_at'))}").classes(
                                    "text-xs text-grey-7"
                                )
                                ui.label(f"Fin : {_format_date(run.get('finished_at'))}").classes(
                                    "text-xs text-grey-7"
                                )
                            with ui.row().classes("items-center gap-2"):
                                badge_statut(run.get("status", "?"))
                                ui.button(
                                    "Ouvrir",
                                    icon="open_in_new",
                                    on_click=lambda r=run: ui.navigate.to(f"/runs/{r['run_id']}"),
                                ).props("flat")

        await refresh()
        ui.button("Rafraichir", icon="refresh", on_click=refresh).props("outline")


@ui.page("/runs/{run_id}")
async def run_detail_page(run_id: str) -> None:
    _install_theme()
    with page_frame("Run live"):
        try:
            initial = await get_rapport(run_id)
        except Exception as exc:  # noqa: BLE001
            ui.label(f"Run introuvable ou API indisponible : {exc}").classes("text-negative")
            return

        completed: set[str] = set()
        awaiting_hitl = initial.get("status") == "awaiting_hitl"

        with ui.card().classes("glass-card w-full p-5"):
            with ui.row().classes("items-center justify-between w-full"):
                with ui.column().classes("gap-1"):
                    ui.label("Execution du pipeline").classes("section-title text-4xl font-black text-primary")
                    ui.label(run_id).classes("font-mono text-sm text-grey-7")
                status_box = ui.row().classes("items-center gap-2")
                with status_box:
                    badge_statut(initial.get("status", "?"))

            diagram = ui.mermaid(_build_mermaid(completed, awaiting_hitl)).classes("w-full")

        hitl_box = ui.column().classes("w-full gap-3")
        timeline = ui.column().classes("w-full gap-2")
        result_box = ui.column().classes("w-full gap-3")

        def update_status(status: str) -> None:
            status_box.clear()
            with status_box:
                badge_statut(status)

        def add_event(event_type: str, data: dict[str, Any]) -> None:
            with timeline:
                with ui.card().classes("timeline-item w-full p-3"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(_event_title(event_type, data)).classes("font-bold")
                        ui.label(data.get("ts", "")).classes("text-xs text-grey-6")
                    if data:
                        ui.markdown(f"```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```").classes(
                            "text-xs w-full"
                        )

        async def render_report() -> None:
            result_box.clear()
            try:
                rapport = await get_rapport(run_id)
            except Exception as exc:  # noqa: BLE001
                with result_box:
                    ui.label(f"Rapport non chargeable : {exc}").classes("text-negative")
                return

            update_status(rapport.get("status", "?"))
            with result_box:
                with ui.card().classes("glass-card w-full p-5"):
                    ui.label("Synthese").classes("text-2xl font-bold text-primary")
                    if rapport.get("erreur"):
                        ui.label(rapport["erreur"]).classes("text-negative")
                    rows = _candidate_rows(rapport.get("candidats"))
                    if rows:
                        ui.table(columns=_candidate_columns(), rows=rows, row_key="nom").classes("w-full")
                    if rapport.get("rapport"):
                        ui.button(
                            "Ouvrir le rapport complet",
                            icon="article",
                            on_click=lambda: ui.navigate.to(f"/rapport/{run_id}"),
                        ).props("unelevated")

        def render_hitl(candidats: list[dict]) -> None:
            hitl_box.clear()
            with hitl_box:
                with ui.card().classes("glass-card w-full p-5 gap-3"):
                    ui.label("Decision humaine requise avant A7").classes(
                        "text-2xl font-bold text-secondary"
                    )
                    ui.label(
                        "Approuver la liste, tout rejeter, ou editer le JSON puis reprendre le pipeline."
                    ).classes("text-grey-8")
                    if candidats:
                        ui.table(
                            columns=_candidate_columns(),
                            rows=_candidate_rows(candidats),
                            row_key="nom",
                        ).classes("w-full")
                    editor = ui.textarea(
                        label="candidats_retenus pour action=edit",
                        value=json.dumps(candidats, ensure_ascii=False, indent=2),
                    ).props("outlined autogrow").classes("w-full font-mono")

                    async def decide(action: str) -> None:
                        payload = None
                        if action == "edit":
                            try:
                                payload = json.loads(editor.value or "[]")
                            except json.JSONDecodeError as exc:
                                ui.notify(f"JSON invalide : {exc}", type="negative")
                                return
                            if not isinstance(payload, list):
                                ui.notify("Le JSON doit etre une liste de candidats.", type="negative")
                                return
                        try:
                            await submit_hitl(run_id, action, payload)
                        except httpx.HTTPError as exc:
                            ui.notify(f"Decision refusee par l'API : {exc}", type="negative")
                            return
                        hitl_box.clear()
                        update_status("running")
                        ui.notify("Decision envoyee, reprise du pipeline.", type="positive")

                    async def approve() -> None:
                        await decide("approve")

                    async def skip() -> None:
                        await decide("skip")

                    async def edit() -> None:
                        await decide("edit")

                    with ui.row().classes("gap-2"):
                        ui.button("Approuver", icon="check", on_click=approve).props("unelevated")
                        ui.button("Tout rejeter", icon="block", on_click=skip).props(
                            "outline color=negative"
                        )
                        ui.button("Reprendre avec le JSON", icon="edit", on_click=edit).props("outline")

        with ui.card().classes("glass-card w-full p-5"):
            ui.label("Timeline live").classes("text-2xl font-bold text-primary")
            with timeline:
                ui.label("Connexion au flux SSE...").classes("text-grey-7")

        async def consume_stream() -> None:
            first = True
            async for event in stream_events(run_id):
                if first:
                    timeline.clear()
                    first = False

                event_type = event.get("type", "unknown")
                data = event.get("data", {})
                add_event(event_type, data)

                if event_type == "node_completed":
                    completed.add(data.get("node", ""))
                    diagram.content = _build_mermaid(completed, awaiting_hitl=False)
                    diagram.update()
                elif event_type == "awaiting_hitl":
                    update_status("awaiting_hitl")
                    render_hitl(data.get("candidats", []))
                    diagram.content = _build_mermaid(completed, awaiting_hitl=True)
                    diagram.update()
                elif event_type == "hitl_decision":
                    update_status("running")
                    diagram.content = _build_mermaid(completed, awaiting_hitl=False)
                    diagram.update()
                elif event_type in {"run_done", "run_error", "stream_closed", "connection_error"}:
                    await render_report()

        background_tasks.create(consume_stream())
        await render_report()


@ui.page("/rapport/{run_id}")
async def rapport_page(run_id: str) -> None:
    _install_theme()
    with page_frame("Rapport"):
        try:
            rapport = await get_rapport(run_id)
        except Exception as exc:  # noqa: BLE001
            ui.label(f"Impossible de charger le rapport : {exc}").classes("text-negative")
            return

        rows = _candidate_rows(rapport.get("candidats"))
        stats = _candidate_stats(rapport.get("candidats"))
        score_stats = _scores_stats(rapport.get("candidats"))
        report_markdown = rapport.get("rapport") or ""
        recherche_section = _extract_report_section(report_markdown, "Recherches effectuées")
        execution_metrics = _parse_execution_metrics(report_markdown)

        with ui.card().classes("glass-card w-full p-5 gap-4"):
            with ui.row().classes("items-center justify-between w-full"):
                ui.label("Rapport final").classes("section-title text-4xl font-black text-primary")
                badge_statut(rapport.get("status", "?"))
            with ui.row().classes("items-center gap-3 text-sm text-grey-7"):
                ui.label(run_id).classes("font-mono")
                ui.label(f"Démarré : {_format_date(rapport.get('started_at'))}")
                ui.label(f"Terminé : {_format_date(rapport.get('finished_at'))}")

        with ui.row().classes("w-full gap-3"):
            for label, value, tone in [
                ("Total candidats", stats["total"], "text-primary"),
                ("Valides", stats["valide"], "text-green-8"),
                ("Douteux", stats["douteux"], "text-orange-8"),
                ("Invalides", stats["invalide"], "text-red-8"),
                ("Score max", f"{score_stats['max']:.1f}", "text-primary"),
                ("Score moyen", f"{score_stats['moyenne']:.1f}", "text-primary"),
            ]:
                with ui.card().classes("metric-card p-4 grow min-w-32"):
                    ui.label(str(value)).classes(f"text-3xl font-black {tone}")
                    ui.label(label).classes("text-sm text-grey-7")

        with ui.card().classes("glass-card w-full p-5 gap-4"):
            ui.label("Répartition des statuts").classes("text-2xl font-bold text-primary")
            ui.echart(_status_chart_options(stats)).classes("w-full h-80")

        with ui.tabs().classes("w-full") as tabs:
            tab_candidats = ui.tab("Candidats", icon="groups")
            tab_recherches = ui.tab("Recherches", icon="manage_search")
            tab_metriques = ui.tab("Métriques", icon="bar_chart")
            tab_rapport = ui.tab("Rapport complet", icon="article")

        with ui.tab_panels(tabs, value=tab_candidats).classes("w-full bg-transparent"):
            with ui.tab_panel(tab_candidats).classes("p-0"):
                with ui.card().classes("glass-card w-full p-5 gap-4"):
                    ui.label("Candidats du run").classes("text-2xl font-bold text-primary")
                    if rows:
                        ui.table(columns=_candidate_columns(), rows=rows, row_key="nom").classes("w-full")
                    else:
                        ui.label("Aucun candidat retourné pour ce run.").classes("text-grey-7")

            with ui.tab_panel(tab_recherches).classes("p-0"):
                with ui.card().classes("glass-card w-full p-5 gap-4"):
                    ui.label("Recherches lancées").classes("text-2xl font-bold text-primary")
                    if recherche_section:
                        ui.markdown(recherche_section).classes("report-markdown w-full")
                    else:
                        ui.label("Aucune recherche détaillée disponible pour ce run.").classes("text-grey-7")

            with ui.tab_panel(tab_metriques).classes("p-0"):
                with ui.card().classes("glass-card w-full p-5 gap-4"):
                    ui.label("Métriques d'exécution").classes("text-2xl font-bold text-primary")
                    with ui.row().classes("w-full gap-3"):
                        for label, value in [
                            ("Run métriques", execution_metrics["run_id"]),
                            ("Durée totale", f"{execution_metrics['duree_totale_s']:.1f}s"),
                            ("Étapes mesurées", len(execution_metrics["steps"])),
                            (
                                "Étape la plus lente",
                                execution_metrics["slowest"]["etape"] if execution_metrics["slowest"] else "-",
                            ),
                        ]:
                            with ui.card().classes("metric-card p-4 grow min-w-32"):
                                ui.label(str(value)).classes("text-2xl font-black text-primary")
                                ui.label(label).classes("text-sm text-grey-7")

                    chart_options = _metrics_chart_options(execution_metrics)
                    if chart_options:
                        ui.label("Temps par étape").classes("text-lg font-bold text-primary")
                        ui.echart(chart_options).classes("w-full h-96")

                    if execution_metrics["steps"]:
                        ui.table(
                            columns=[
                                {"name": "etape", "label": "Étape", "field": "etape", "align": "left"},
                                {"name": "duree_label", "label": "Durée", "field": "duree_label", "align": "left"},
                                {"name": "details", "label": "Détails", "field": "details", "align": "left"},
                            ],
                            rows=execution_metrics["steps"],
                            row_key="etape",
                        ).classes("w-full")
                    elif execution_metrics["raw"]:
                        ui.markdown(f"```text\n{execution_metrics['raw']}\n```").classes("w-full")
                    else:
                        ui.label("Aucune métrique détaillée disponible pour ce run.").classes("text-grey-7")

            with ui.tab_panel(tab_rapport).classes("p-0"):
                with ui.card().classes("glass-card w-full p-5 gap-4"):
                    ui.label("Rapport Markdown").classes("text-2xl font-bold text-primary")
                    ui.markdown(
                        report_markdown or "Rapport pas encore disponible."
                    ).classes("report-markdown w-full")


@ui.page("/rag")
async def rag_page() -> None:
    _install_theme()
    with page_frame("Memoire RAG"):
        ui.label("Memoire vectorielle").classes("section-title text-4xl font-black text-primary")
        try:
            summary = await get_rag_summary()
        except Exception as exc:  # noqa: BLE001
            ui.label(f"Impossible de lire l'etat RAG : {exc}").classes("text-negative")
            return

        with ui.row().classes("w-full gap-3"):
            for label, value in [
                ("Candidats memorises", summary.get("candidats", 0)),
                ("Fiches de poste", summary.get("fiches_poste", 0)),
                ("Repertoire", summary.get("persist_dir", "-")),
            ]:
                with ui.card().classes("metric-card p-4 grow"):
                    ui.label(str(value)).classes("text-3xl font-black text-primary")
                    ui.label(label).classes("text-sm text-grey-7")
        if summary.get("error"):
            ui.label(summary["error"]).classes("text-negative")

        with ui.card().classes("glass-card w-full p-5 gap-3"):
            ui.label("Recherche de profils similaires").classes("text-2xl font-bold text-primary")
            query = ui.textarea(label="Profil ou mots-cles", placeholder="Python FastAPI RAG Docker...").props(
                "outlined autogrow"
            ).classes("w-full")
            fiche = ui.textarea(
                label="Fiche de poste de contexte (optionnel)",
                placeholder="Si renseignee, la recherche est calibree sur les fiches similaires.",
            ).props("outlined autogrow").classes("w-full")
            results_box = ui.column().classes("w-full")

            async def run_search() -> None:
                if not query.value or not query.value.strip():
                    ui.notify("Saisissez un profil ou des mots-cles.", type="warning")
                    return
                results_box.clear()
                with results_box:
                    ui.spinner(size="lg")
                try:
                    payload = await search_rag(query.value.strip(), fiche.value.strip() if fiche.value else None)
                except Exception as exc:  # noqa: BLE001
                    results_box.clear()
                    with results_box:
                        ui.label(f"Recherche impossible : {exc}").classes("text-negative")
                    return
                results_box.clear()
                rows = payload.get("results", [])
                with results_box:
                    if rows:
                        ui.table(
                            columns=[
                                {"name": "nom", "label": "Nom", "field": "nom", "align": "left"},
                                {"name": "score", "label": "Score", "field": "score", "align": "left"},
                                {"name": "similarite", "label": "Similarite", "field": "similarite", "align": "left"},
                                {"name": "source", "label": "Source", "field": "source", "align": "left"},
                                {"name": "remarques", "label": "Remarques", "field": "remarques", "align": "left"},
                            ],
                            rows=rows,
                            row_key="nom",
                        ).classes("w-full")
                    else:
                        ui.label("Aucun profil similaire trouve.").classes("text-grey-7")

            ui.button("Rechercher", icon="search", on_click=run_search).props("unelevated")
            with results_box:
                ui.label("La recherche charge le modele d'embedding uniquement au clic.").classes(
                    "text-xs text-grey-7"
                )


@ui.page("/metriques")
async def metrics_page() -> None:
    _install_theme()
    with page_frame("Metriques"):
        ui.label("Observabilite").classes("section-title text-4xl font-black text-primary")
        try:
            payload = await get_metrics_summary()
        except Exception as exc:  # noqa: BLE001
            ui.label(f"Impossible de charger les metriques : {exc}").classes("text-negative")
            return

        current = payload.get("current", {})
        history = payload.get("history", [])

        with ui.row().classes("w-full gap-3"):
            with ui.card().classes("metric-card p-4 grow"):
                ui.label(str(current.get("run_id", "-"))).classes("text-xl font-black text-primary")
                ui.label("Run courant").classes("text-sm text-grey-7")
            with ui.card().classes("metric-card p-4 grow"):
                ui.label(f"{current.get('duree_totale_s', 0)} s").classes("text-3xl font-black text-primary")
                ui.label("Duree en memoire").classes("text-sm text-grey-7")
            with ui.card().classes("metric-card p-4 grow"):
                ui.label(str(len(current.get("etapes", {})))).classes("text-3xl font-black text-primary")
                ui.label("Etapes tracees").classes("text-sm text-grey-7")

        rows = []
        for name, data in (current.get("etapes") or {}).items():
            rows.append({
                "etape": name,
                "duree_s": data.get("duree_s", ""),
                "details": ", ".join(
                    f"{k}={v}" for k, v in data.items() if k not in {"debut", "fin", "duree_s"}
                )[:220],
            })
        with ui.card().classes("glass-card w-full p-5"):
            ui.label("Etapes du run courant").classes("text-2xl font-bold text-primary")
            if rows:
                ui.table(
                    columns=[
                        {"name": "etape", "label": "Etape", "field": "etape", "align": "left"},
                        {"name": "duree_s", "label": "Duree (s)", "field": "duree_s", "align": "left"},
                        {"name": "details", "label": "Details", "field": "details", "align": "left"},
                    ],
                    rows=rows,
                    row_key="etape",
                ).classes("w-full")
            else:
                ui.label("Aucune etape en memoire. Lancez un run pour alimenter cette vue.").classes("text-grey-7")

        history_rows = [
            {
                "file": item.get("_file", ""),
                "run_id": item.get("run_id", ""),
                "duree_totale_s": item.get("duree_totale_s", ""),
                "etapes": len(item.get("etapes", {})),
            }
            for item in history
        ]
        with ui.card().classes("glass-card w-full p-5"):
            ui.label("Derniers exports logs/metriques_*.json").classes("text-2xl font-bold text-primary")
            if history_rows:
                ui.table(
                    columns=[
                        {"name": "file", "label": "Fichier", "field": "file", "align": "left"},
                        {"name": "run_id", "label": "Run", "field": "run_id", "align": "left"},
                        {
                            "name": "duree_totale_s",
                            "label": "Duree totale (s)",
                            "field": "duree_totale_s",
                            "align": "left",
                        },
                        {"name": "etapes", "label": "Etapes", "field": "etapes", "align": "left"},
                    ],
                    rows=history_rows,
                    row_key="file",
                ).classes("w-full")
            else:
                ui.label("Aucun export de metriques trouve dans logs/.").classes("text-grey-7")


def main() -> None:
    ui.run(
        title="SMA Recrutement",
        host=os.getenv("UI_HOST", "0.0.0.0"),
        port=int(os.getenv("UI_PORT", "8080")),
        reload=os.getenv("UI_RELOAD", "false").lower() == "true",
        show=False,
        show_welcome_message=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
