"""
Mémoire RAG — Stockage vectoriel des candidats évalués, calibré par fiche de poste.

Utilise ChromaDB (local, gratuit, aucun serveur requis) avec
SentenceTransformers pour les embeddings (all-MiniLM-L6-v2, ~80 MB).

Deux collections :
    - fiches_poste       : embeddings des fiches de poste passées
    - candidats_evalues  : embeddings des profils, reliés à leur fiche via fiche_id

Rôle dans le pipeline :
    Écriture (A8) : on upsert la fiche courante, puis chaque candidat validé
                    avec un lien vers cette fiche.
    Lecture  (A4) : on cherche d'abord les fiches similaires à la fiche
                    courante (au-dessus d'un seuil de similarité). Si aucune
                    fiche comparable n'existe, on ne renvoie RIEN (éviter
                    le biais de calibration inter-postes). Sinon, on
                    restreint la recherche des candidats similaires aux
                    seules fiches pertinentes.

Persistence : ./data/chromadb/  (créé automatiquement au premier run)
"""

import hashlib
import os
import time
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from src.logger import get_logger

_log = get_logger("tools.rag")

_PERSIST_DIR = os.getenv("CHROMADB_DIR", "./data/chromadb")
_CANDIDATS_COLLECTION = "candidats_evalues"
_FICHES_COLLECTION = "fiches_poste"
_EMBED_MODEL = "all-MiniLM-L6-v2"   # ~80 MB, téléchargé une seule fois

# Seuil de similarité fiche↔fiche au-dessus duquel on considère qu'une fiche
# stockée est suffisamment proche de la fiche courante pour que ses candidats
# soient une référence de calibration légitime.
_SEUIL_FICHE_DEFAUT = 0.5


def hash_fiche(texte: str) -> str:
    """Hash stable d'une fiche de poste — sert d'identifiant déterministe.

    Même texte (au whitespace près) → même id, ce qui garantit l'idempotence
    du upsert si la même fiche est passée deux fois.
    """
    normalise = " ".join(texte.split()).lower()
    return hashlib.sha1(normalise.encode("utf-8")).hexdigest()[:12]


class MemoireRAG:
    """Interface ChromaDB pour la mémoire vectorielle, calibrée par fiche."""

    def __init__(self, persist_dir: str = _PERSIST_DIR):
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._ef = None
        self._candidats = self._open_collection(_CANDIDATS_COLLECTION)
        self._fiches = self._open_collection(_FICHES_COLLECTION)
        _log.info(
            "Mémoire RAG initialisée (%d candidats, %d fiches) → %s",
            self._candidats.count(), self._fiches.count(), persist_dir,
        )

    def _open_collection(self, name: str):
        """Ouvre une collection avec SentenceTransformer, ou réutilise
        l'embedding function persistée si la base existe déjà.

        ChromaDB persiste la configuration d'embedding. Une base créée avec
        l'embedding par défaut refuse ensuite `SentenceTransformer`, ce qui
        ne doit pas bloquer le pipeline : dans ce cas, on garde l'existant.
        """
        try:
            return self._client.get_collection(name)
        except Exception:
            pass

        if self._ef is None:
            self._ef = SentenceTransformerEmbeddingFunction(model_name=_EMBED_MODEL)

        try:
            return self._client.get_or_create_collection(
                name=name,
                embedding_function=self._ef,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            message = str(exc).lower()
            if "embedding function conflict" not in message:
                raise
            _log.warning(
                "Collection ChromaDB '%s' déjà créée avec une autre embedding function ; "
                "réouverture avec sa configuration persistée.",
                name,
            )
            return self._client.get_collection(name)

    # ------------------------------------------------------------------
    # Écriture
    # ------------------------------------------------------------------

    def ajouter_fiche_poste(self, fiche_texte: str) -> str:
        """Upsert la fiche de poste dans la collection dédiée.

        Retourne le fiche_id (hash) qui servira à rattacher les candidats.
        """
        if not fiche_texte or not fiche_texte.strip():
            return ""
        fiche_id = hash_fiche(fiche_texte)
        document = fiche_texte[:3000]
        try:
            self._fiches.upsert(
                ids=[fiche_id],
                documents=[document],
                metadatas=[{"longueur": len(fiche_texte)}],
            )
        except Exception as e:
            _log.warning("Erreur upsert fiche_poste : %s", e)
        return fiche_id

    def ajouter_candidat(
        self,
        candidat_id: str,
        nom: str,
        profil_brut: str,
        score: float,
        source: str,
        remarques: str = "",
        fiche_id: str = "",
        statut: str = "valide",
        url: str = "",
    ) -> None:
        """Stocke un candidat évalué dans la base vectorielle.

        Le champ fiche_id rattache le candidat à la fiche de poste pour
        laquelle il a été évalué : c'est ce qui permet à la lecture
        ultérieure de ne remonter que des candidats évalués dans un
        contexte de poste comparable.
        statut et url permettent la blacklist inter-runs et le cache de score.
        """
        document = profil_brut[:2000] if profil_brut.strip() else f"Profil de {nom}"

        metadata = {
            "nom": nom,
            "score": score,
            "source": source,
            "remarques": remarques[:500],
            "fiche_id": fiche_id,
            "statut": statut,
            "url": url or "",
            "last_seen": time.time(),
        }

        try:
            self._candidats.upsert(
                ids=[candidat_id],
                documents=[document],
                metadatas=[metadata],
            )
        except Exception as e:
            _log.warning("Erreur upsert ChromaDB pour %s : %s", nom, e)

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def _fiches_similaires_ids(
        self, fiche_texte: str, seuil: float, n_max: int = 3
    ) -> list[str]:
        """Retourne les fiche_ids dont la similarité cosine avec la fiche
        courante dépasse le seuil. Liste vide si aucune fiche comparable.
        """
        total = self._fiches.count()
        if total == 0 or not fiche_texte.strip():
            return []

        n = min(n_max, total)
        try:
            results = self._fiches.query(
                query_texts=[fiche_texte[:3000]],
                n_results=n,
                include=["distances"],
            )
        except Exception as e:
            _log.warning("Erreur query fiches_poste : %s", e)
            return []

        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        retenus = [
            fid for fid, dist in zip(ids, distances)
            if (1 - dist) >= seuil
        ]
        return retenus

    def rechercher_similaires(
        self,
        profil_brut: str,
        fiche_poste: str | None = None,
        n_results: int = 3,
        seuil_fiche: float = _SEUIL_FICHE_DEFAUT,
    ) -> list[dict]:
        """Recherche les candidats les plus similaires au profil donné,
        restreinte aux fiches de poste comparables à la fiche courante.

        Si fiche_poste est None → comportement legacy (recherche globale,
        sans filtrage par contexte de poste). Conservé pour rétrocompat.

        Si fiche_poste est fourni mais aucune fiche stockée n'atteint
        seuil_fiche, retourne [] plutôt que d'injecter un signal de
        calibration hors-contexte.

        Returns:
            Liste de dicts {nom, score, source, remarques, similarite}.
        """
        total = self._candidats.count()
        if total == 0:
            return []

        n = min(n_results, total)
        query = profil_brut[:2000] if profil_brut.strip() else "profil développeur"

        where_clause: dict | None = None
        if fiche_poste is not None:
            fiche_ids = self._fiches_similaires_ids(fiche_poste, seuil_fiche)
            if not fiche_ids:
                _log.info(
                    "RAG : aucune fiche stockée au-dessus du seuil %.2f → contexte non injecté.",
                    seuil_fiche,
                )
                return []
            where_clause = {"fiche_id": {"$in": fiche_ids}}

        try:
            kwargs = {
                "query_texts": [query],
                "n_results": n,
                "include": ["metadatas", "distances"],
            }
            if where_clause is not None:
                kwargs["where"] = where_clause
            results = self._candidats.query(**kwargs)
        except Exception as e:
            _log.warning("Erreur query candidats : %s", e)
            return []

        similaires = []
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for meta, dist in zip(metadatas, distances):
            similaires.append({
                "nom": meta.get("nom", "?"),
                "score": meta.get("score", 0),
                "source": meta.get("source", "?"),
                "remarques": meta.get("remarques", ""),
                "similarite": round(1 - dist, 3),
            })

        return similaires

    def get_candidats_connus(
        self,
        fiche_poste: str,
        seuil_fiche: float = 0.75,
        max_age_jours: int = 30,
    ) -> list[dict]:
        """Retourne les candidats validés pour une fiche similaire, récents.

        Utilisé par injection_rag pour compléter les résultats d'un run
        avec des profils déjà connus depuis la mémoire inter-runs.

        Returns liste de dicts {candidat_id, nom, score, source, remarques, url}.
        """
        if self._candidats.count() == 0 or not fiche_poste.strip():
            return []

        fiche_ids_ok = set(self._fiches_similaires_ids(fiche_poste, seuil_fiche))
        if not fiche_ids_ok:
            return []

        cutoff = time.time() - max_age_jours * 86400

        try:
            results = self._candidats.get(
                where={"statut": {"$eq": "valide"}},
                include=["metadatas"],
                limit=50,
            )
        except Exception as e:
            _log.warning("Erreur get_candidats_connus : %s", e)
            return []

        ids = results.get("ids", [])
        metas = results.get("metadatas", []) or []

        connus = []
        for cid, meta in zip(ids, metas):
            if meta.get("fiche_id", "") not in fiche_ids_ok:
                continue
            if meta.get("last_seen", 0) < cutoff:
                continue
            connus.append({
                "candidat_id": cid,
                "nom": meta.get("nom", "?"),
                "score": meta.get("score", 0),
                "source": meta.get("source", ""),
                "remarques": meta.get("remarques", ""),
                "url": meta.get("url", ""),
            })

        connus.sort(key=lambda x: x["score"], reverse=True)
        return connus[:10]

    def est_blackliste(self, url: str) -> bool:
        """Vrai si cette URL a déjà été évaluée et marquée invalide.

        Requête purement metadata (pas d'embedding) → très rapide.
        Retourne False en cas d'erreur pour ne jamais bloquer le pipeline.
        """
        if not url or self._candidats.count() == 0:
            return False
        try:
            results = self._candidats.get(
                where={"url": {"$eq": url}},
                include=["metadatas"],
                limit=10,
            )
            return any(m.get("statut") == "invalide" for m in results.get("metadatas", []))
        except Exception as e:
            _log.debug("Blacklist check ignoré (champ manquant ou erreur) : %s", e)
            return False

    def get_score_cache(
        self,
        url: str,
        fiche_poste: str | None = None,
        seuil_fiche: float = 0.85,
    ) -> dict | None:
        """Retourne le score mis en cache pour cette URL si la fiche est similaire.

        Conditions :
        - L'URL a déjà été évaluée avec statut "valide"
        - La fiche de poste stockée est suffisamment similaire (cosine >= seuil_fiche)

        Returns dict {nom, score, source, remarques} ou None si pas de cache valide.
        Retourne None en cas d'erreur pour ne jamais bloquer le pipeline.
        """
        if not url or self._candidats.count() == 0:
            return None
        try:
            results = self._candidats.get(
                where={"url": {"$eq": url}},
                include=["metadatas"],
                limit=10,
            )
        except Exception as e:
            _log.debug("Cache check ignoré : %s", e)
            return None

        metas = [m for m in results.get("metadatas", []) if m.get("statut") == "valide"]
        if not metas:
            return None

        if fiche_poste is not None:
            fiche_ids_ok = set(self._fiches_similaires_ids(fiche_poste, seuil_fiche))
            metas = [m for m in metas if m.get("fiche_id", "") in fiche_ids_ok]
            if not metas:
                return None

        best = max(metas, key=lambda m: m.get("score", 0))
        return {
            "nom": best.get("nom", "?"),
            "score": best.get("score", 0),
            "source": best.get("source", "?"),
            "remarques": best.get("remarques", ""),
        }

    def compter(self) -> int:
        """Retourne le nombre total de candidats en base."""
        return self._candidats.count()

    def compter_fiches(self) -> int:
        """Retourne le nombre de fiches de poste stockées."""
        return self._fiches.count()


# ---------------------------------------------------------------------------
# Singleton — une seule instance par process
# ---------------------------------------------------------------------------
_instance: MemoireRAG | None = None


def get_memoire() -> MemoireRAG:
    """Retourne l'instance globale de la mémoire RAG (lazy init)."""
    global _instance
    if _instance is None:
        _instance = MemoireRAG()
    return _instance
