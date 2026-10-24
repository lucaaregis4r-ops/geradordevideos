"""Semantic Media Ranker with multimodal evaluation and configurable weighted scoring.

Implements Section 31:
score = 0.60 * semantic + 0.15 * resolution + 0.10 * orientation + 0.10 * motion + 0.05 * previous_approval
"""

from __future__ import annotations
import json
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from app.config import config
from .schemas import MediaCandidate
from .thumbnailer import Thumbnailer


BILINGUAL_LEXICON: Dict[str, set[str]] = {
    # Clothing / Retail
    "shirt": {"camiseta", "camisa", "roupa"},
    "tshirt": {"camiseta", "camisa"},
    "clothing": {"roupa", "vestuário", "peça"},
    "clothes": {"roupa", "roupas"},
    "store": {"loja", "shopping", "comércio", "vitrine"},
    "shop": {"loja", "comércio"},
    "mall": {"shopping", "loja"},
    "price": {"preço", "valor", "reais", "custa"},
    "tag": {"etiqueta", "preço"},
    "mannequin": {"manequim", "vitrine", "exposta"},
    "cotton": {"algodão", "tecido"},
    "money": {"dinheiro", "reais", "dólar", "moeda"},
    "cash": {"dinheiro", "reais"},
    # Production / Factory
    "factory": {"fábrica", "indústria", "confecção"},
    "sewing": {"costura", "costurar"},
    "machine": {"máquina", "equipamento"},
    "fabric": {"tecido", "pano"},
    "thread": {"fio", "linha"},
    "worker": {"trabalhador", "operário", "trabalho"},
    "labor": {"trabalho", "trabalhador", "operário"},
    "industry": {"indústria", "fábrica"},
    "farm": {"campo", "fazenda", "agricultura"},
    "harvest": {"colheita", "safra"},
    # Science / Space
    "space": {"espaço", "espacial", "cosmos"},
    "rocket": {"foguete", "nave"},
    "planet": {"planeta", "órbita"},
    "star": {"estrela", "astro"},
    "telescope": {"telescópio", "observatório"},
    "galaxy": {"galáxia", "universo"},
    "science": {"ciência", "científico"},
    # Sports
    "soccer": {"futebol", "bola", "gol"},
    "football": {"futebol", "campo"},
    "ball": {"bola", "jogo"},
    "stadium": {"estádio", "arena"},
    "player": {"jogador", "atleta"},
    "game": {"jogo", "partida"},
    "court": {"quadra", "campo"},
}


class SemanticRanker:
    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        thumbnailer: Optional[Thumbnailer] = None,
    ):
        # Configurable weights (Section 31)
        self.weights = {
            "semantic": 0.60,
            "resolution": 0.15,
            "orientation": 0.10,
            "motion": 0.10,
            "previous_approval": 0.05,
        }
        if weights:
            self.weights.update(weights)

        self.thumbnailer = thumbnailer or Thumbnailer()

    def evaluate_semantic_fit(
        self,
        candidate: MediaCandidate,
        scene_narration: str,
        scene_intent: str,
    ) -> float:
        """Evaluates semantic similarity between candidate metadata and scene narration/intent.

        No artificial 0.90 floor for smart_library — local assets compete fairly on relevance.
        Prior editorial curation is captured solely via the previous_approval weight (0.05).
        """
        context = hashlib.sha256(f"metadata-v2:{scene_narration}:{scene_intent}".encode()).hexdigest()
        if candidate.evaluation_context == context and candidate.semantic_status in {"visual_verified", "reviewed"}:
            return candidate.semantic_score
        candidate.evaluation_context = context
        candidate.semantic_status = "metadata_only" if candidate.description or candidate.tags else "unverified"
        if candidate.semantic_status == "unverified":
            return 0.0

        # Stopwords in PT and EN to prevent trivial conjunction/preposition matches
        stopwords = {
            "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
            "para", "por", "com", "sem", "um", "uma", "uns", "umas",
            "o", "a", "os", "as", "que", "se", "e", "ou", "mas", "como", "mais",
            "the", "a", "an", "in", "on", "at", "for", "of", "to", "and", "or",
            "is", "are", "with", "from", "by", "this", "that"
        }

        # Build token set from candidate attributes (query, category, creator, source)
        cand_text = f"{candidate.description} {' '.join(candidate.tags)}"
        cand_words = {
            w for w in re.findall(r"\w+", cand_text.lower())
            if len(w) > 2 and w not in stopwords
        }

        # Expand candidate words using bilingual lexicon (EN -> PT concepts)
        expanded_cand_words = set(cand_words)
        for w in cand_words:
            if w in BILINGUAL_LEXICON:
                expanded_cand_words.update(BILINGUAL_LEXICON[w])

        # Build token set from scene context
        scene_text = f"{scene_narration} {scene_intent}"
        scene_words = {
            w for w in re.findall(r"\w+", scene_text.lower())
            if len(w) > 2 and w not in stopwords
        }

        overlap = expanded_cand_words.intersection(scene_words)
        if overlap:
            base_score = 0.40 + min(0.55, len(overlap) * 0.15)
        else:
            # Check for partial prefix/stem matches (e.g. camis- vs camiseta)
            partial_matches = sum(
                1 for cw in expanded_cand_words
                if any(cw[:4] == sw[:4] for sw in scene_words if len(sw) >= 4 and len(cw) >= 4)
            )
            if partial_matches > 0:
                base_score = 0.30 + min(0.30, partial_matches * 0.10)
            else:
                base_score = 0.20  # Completely irrelevant candidate

        # Penalize if visual quality is known to be poor
        if candidate.visual_quality_score > 0 and candidate.visual_quality_score < 0.20:
            base_score *= 0.5

        return min(1.0, max(0.15, round(base_score, 2)))

    def rank_candidates(
        self,
        scene_narration: str,
        scene_intent: str,
        candidates: List[MediaCandidate],
        top_k: int = 3,
    ) -> List[MediaCandidate]:
        """Applies multimodal/semantic scoring and produces the final ranked top_k candidates."""
        for c in candidates:
            # 1. Semantic score
            sem = self.evaluate_semantic_fit(c, scene_narration, scene_intent)
            c.semantic_score = sem

            # 2. Extract thumbnail if local clip exists
            if c.local_path and not c.thumbnail:
                thumb = self.thumbnailer.extract_thumbnail(c.local_path)
                if thumb:
                    c.thumbnail = thumb

            # 3. Component scores
            # Resolution: 1080p -> 1.0, 720p -> 0.7, other -> 0.4
            res_score = 1.0 if (c.height >= 1920 or c.width >= 1080) else (0.7 if c.height >= 1280 else 0.4)

            # Orientation: vertical 9:16 -> 1.0, square -> 0.6, landscape -> 0.3
            ratio = c.width / c.height if c.height > 0 else 0.5625
            if abs(ratio - 0.5625) < 0.05 or ratio < 0.7:
                ori_score = 1.0
            elif abs(ratio - 1.0) < 0.05:
                ori_score = 0.6
            else:
                ori_score = 0.3

            # Motion: default 0.8
            mot_score = 0.0  # Unmeasured movement is not evidence of action.

            # Previous approval: 1.0 for smart_library or approved cache, 0.0 otherwise
            app_score = 1.0 if c.provider in {"smart_library", "local"} else 0.0

            # Composite weighted score
            final = (
                self.weights["semantic"] * sem
                + self.weights["resolution"] * res_score
                + self.weights["orientation"] * ori_score
                + self.weights["motion"] * mot_score
                + self.weights["previous_approval"] * app_score
            )
            c.final_score = round(min(1.0, max(0.0, final)), 3)

        # Sort descending by final composite score
        ranked = sorted(candidates, key=lambda c: c.final_score, reverse=True)
        return ranked[:top_k]
