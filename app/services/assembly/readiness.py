"""Actionable coverage report; preview never bypasses structural failures."""
from pathlib import Path


def readiness_report(plan, scene_plan) -> dict:
    scenes = {s.scene_id: s for s in scene_plan.scenes}
    pending = []
    for segment in plan.segments:
        reasons = []
        if not segment.asset_path or not Path(segment.asset_path).is_file():
            reasons.append('Mídia ausente')
        if getattr(segment, 'is_synthetic', False) or segment.asset_id.startswith(('missing_', 'syn_')) or any(
            x in (segment.asset_path or '') for x in ('fallback_', 'synthetic_')
        ):
            reasons.append('Imagem provisória')
        scene = scenes.get(segment.scene_ref)
        if reasons:
            pending.append({'segmento': segment.segment_id, 'cena': segment.scene_ref,
                            'motivo': '; '.join(reasons),
                            'narracao': scene.narration if scene else '',
                            'buscas': list(scene.queries) if scene else []})
    return {'total_segments': len(plan.segments), 'pending': pending,
            'covered_segments': len(plan.segments) - len(pending)}


def can_render(score, *, allow_preview: bool = False) -> bool:
    if score.passed:
        return True
    # Editorial relevance can be reviewed in a preview; structural failures cannot.
    soft_prefixes = ('pending_review:', 'semantic_match_avg=', 'visual_diversity=',
                     'consecutive_treatment_violations=')
    return bool(allow_preview and score.alerts and
                all(a.startswith(soft_prefixes) for a in score.alerts))
