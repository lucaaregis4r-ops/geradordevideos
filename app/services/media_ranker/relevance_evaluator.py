"""Optional contextual visual evaluation; no paid service is selected implicitly."""
import hashlib
import json
from pathlib import Path
from typing import Callable, Optional


class RelevanceEvaluator:
    def __init__(self, evaluate: Optional[Callable] = None, budget: int = 0,
                 cache_dir: str | Path = "storage/relevance_cache", version: str = "v1"):
        self.evaluate = evaluate
        self.remaining = budget
        self.cache_dir = Path(cache_dir)
        self.version = version

    def assess(self, candidate, beat, frames: list[str]) -> dict:
        context = {"intent": beat.intent, "subject": beat.subject, "action": beat.action,
                   "required": beat.required_elements, "forbidden": beat.forbidden_elements}
        key = hashlib.sha256(json.dumps([self.version, candidate.content_hash,
            candidate.asset_id, candidate.source_in, candidate.source_out, context], sort_keys=True).encode()).hexdigest()
        cache = self.cache_dir / f"{key}.json"
        if cache.exists():
            return json.loads(cache.read_text())
        if not self.evaluate or self.remaining <= 0 or len(frames) != 3:
            return {"status": "unverified", "score": 0.0, "reason": "visual_review_required"}
        self.remaining -= 1
        result = self.evaluate(frames=frames, context=context)
        score = float(result.get("score", 0))
        if not 0 <= score <= 1:
            raise ValueError("invalid_relevance_score")
        approved = score >= 0.7 and not result.get("missing_elements") and not result.get("forbidden_elements")
        result = {**result, "score": score, "status": "visual_verified" if approved else "rejected", "context": key}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result), encoding="utf-8")
        return result
