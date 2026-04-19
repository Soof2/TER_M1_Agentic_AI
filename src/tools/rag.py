"""
Mémoire RAG — Stockage vectoriel des candidats évalués.

Utilise ChromaDB (local, gratuit, aucun serveur requis) avec
SentenceTransformers pour les embeddings (all-MiniLM-L6-v2, ~80 MB).

Rôle dans le pipeline :
    Écriture : après chaque run, le nœud Persistance (A8) stocke
               les candidats validés avec leur score et remarques.
    Lecture  : avant chaque évaluation, A4 récupère les profils
               similaires pour enrichir son contexte de scoring.

Persistence : ./data/chromadb/  (créé automatiquement au premier run)
"""

import os
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from src.logger import get_logger

_log = get_logger("tools.rag")

_PERSIST_DIR = os.getenv("CHROMADB_DIR", "./data/chromadb")
_COLLECTION_NAME = "candidats_evalues"
_EMBED_MODEL = "all-MiniLM-L6-v2"   # ~80 MB, téléchargé une seule fois


class MemoireRAG:
    """Interface ChromaDB pour la mémoire vectorielle des candidats."""

    def __init__(self, persist_dir: str = _PERSIST_DIR):
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._ef = SentenceTransformerEmbeddingFunction(model_name=_EMBED_MODEL)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        _log.info(
            "Mémoire RAG initialisée (%d candidats en base) → %s",
            self._collection.count(), persist_dir,
        )

    # ------------------------------------------------------------------
    # Écriture
    # ------------------------------------------------------------------

    def ajouter_candidat(
        self,
        candidat_id: str,
        nom: str,
        profil_brut: str,
        score: float,
        source: str,
        remarques: str = "",
    ) -> None:
        """Stocke un candidat évalué dans la base vectorielle.

        Si le candidat existe déjà (même ID), il est mis à jour.
        """
        # ChromaDB exige des documents non vides
        document = profil_brut[:2000] if profil_brut.strip() else f"Profil de {nom}"

        try:
            self._collection.upsert(
                ids=[candidat_id],
                documents=[document],
                metadatas=[{
                    "nom": nom,
                    "score": score,
                    "source": source,
                    "remarques": remarques[:500],
                }],
            )
        except Exception as e:
            _log.warning("Erreur upsert ChromaDB pour %s : %s", nom, e)

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def rechercher_similaires(
        self, profil_brut: str, n_results: int = 3
    ) -> list[dict]:
        """Recherche les candidats les plus similaires au profil donné.

        Args:
            profil_brut: Texte du profil candidat à comparer.
            n_results: Nombre max de résultats.

        Returns:
            Liste de dicts {nom, score, source, remarques, distance}.
            Liste vide si la base est vide ou si la recherche échoue.
        """
        total = self._collection.count()
        if total == 0:
            return []

        n = min(n_results, total)
        query = profil_brut[:2000] if profil_brut.strip() else "profil développeur"

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n,
                include=["metadatas", "distances"],
            )
        except Exception as e:
            _log.warning("Erreur query ChromaDB : %s", e)
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
                "similarite": round(1 - dist, 3),   # cosine distance → similarité
            })

        return similaires

    def compter(self) -> int:
        """Retourne le nombre total de candidats en base."""
        return self._collection.count()


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
