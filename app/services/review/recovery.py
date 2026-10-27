"""Checkpointed recovery of missing/rejected media, without TTS or rendering."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
from typing import Callable
import uuid

from loguru import logger
from app.services.director.schemas import ScenePlan


def media_state(media: dict | None) -> str:
    media = media or {}
    if media.get('semantic_status') == 'rejected':
        return 'rejected'
    path = media.get('local_path', '')
    if not path or not Path(path).is_file():
        return 'missing'
    if media.get('is_synthetic') or str(media.get('asset_id', '')).startswith(('missing_', 'syn_')) or any(
        token in path for token in ('fallback_', 'synthetic_')
    ):
        return 'placeholder'
    if media.get('semantic_status') not in {'reviewed', 'visual_verified', 'planned_graphic'}:
        return 'review'
    return 'ready'


def targets(plan: ScenePlan):
    for scene in plan.scenes:
        for target in scene.visual_beats or [scene]:
            yield scene, target


def diagnosis(plan: ScenePlan) -> list[dict]:
    rows = []
    for scene, target in targets(plan):
        rejection_counts = Counter()
        for candidate in target.media_candidates:
            reason = str(candidate.get('error_detail') or '')
            # Never display raw provider exceptions, signed URLs or credentials.
            category = next((r for r in ('rejected_relevance', 'pending_review', 'rejected_resolution',
                'decode_failed', 'perceptual_duplicate') if reason.startswith(r)), 'outro')
            if reason:
                rejection_counts[category] += 1
        rows.append({'scene': scene.scene_id, 'beat': getattr(target, 'beat_id', None),
            'state': media_state(target.selected_media), 'queries': list(target.queries),
            'candidates': len(target.media_candidates), 'rejections': dict(rejection_counts),
            'attempts': [{k: a.get(k) for k in ('provider', 'query', 'status', 'candidate_count')}
                         for a in getattr(target, 'search_attempts', [])]})
    return rows


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def recover_pending(path: Path, searcher, *, limit: int = 3,
                    progress: Callable[[str, float], None] | None = None) -> dict:
    if not 1 <= limit <= 20:
        raise ValueError('Escolha de 1 a 20 planos por rodada.')
    expected = path.read_text(encoding='utf-8')
    plan = ScenePlan.from_dict(json.loads(expected))
    work = [(s, t) for s, t in targets(plan) if media_state(t.selected_media) in {'missing', 'rejected', 'placeholder'}][:limit]
    searcher.reset()
    from app.services.media_ranker.schemas import MediaCandidate
    for scene, target in targets(plan):
        if media_state(target.selected_media) in {'ready', 'review'}:
            candidate = MediaCandidate.from_dict(target.selected_media)
            searcher.deduplicator.mark_used(candidate, scene_id=getattr(target, 'beat_id', scene.scene_id))
            if not getattr(scene, 'intentional_callback', None):
                searcher.deduplicator.block_asset(candidate.asset_id)
        elif target.selected_media and media_state(target.selected_media) == 'rejected':
            searcher.deduplicator.block_asset(target.selected_media.get('asset_id', ''))
    results = []
    for idx, (scene, target) in enumerate(work):
        key = getattr(target, 'beat_id', scene.scene_id)
        if progress:
            progress(f'Pesquisando {scene.scene_id} / {key}', idx / max(1, len(work)))
        total = float((scene.overlay or {}).get('audio_duration') or
                      (scene.end - scene.start if scene.start is not None and scene.end is not None else scene.duration_hint))
        duration = total
        if scene.visual_beats:
            duration *= max(.01, target.duration) / sum(max(.01, b.duration) for b in scene.visual_beats)
            searcher._beat_context[key] = target
        component = getattr(target, 'component_type', None)
        visual_type = component if component in {'data_card', 'price_tag'} else target.visual_type
        child = replace(scene, scene_id=key, queries=list(target.queries), intent=target.intent,
                        visual_type=visual_type, text_overlay=target.text_overlay,
                        text_level=target.text_level, preferred_motion=target.preferred_motion,
                        visual_beats=[], selected_media=None,
                        media_candidates=[], start=0, end=duration)
        attempt_start = len(searcher.search_attempts)
        try:
            searcher.populate_scene_plan(replace(plan, scenes=[child], total_scenes=1), download_selected=True)
        except Exception as exc:
            logger.warning('Recovery failed for {}: {}', key, type(exc).__name__)
            results.append({'scene': scene.scene_id, 'beat': key, 'status': 'search_failed', 'error': type(exc).__name__})
            continue
        # Preserve approved narration, timeline, audio and every other selection.
        if child.selected_media:
            target.selected_media = child.selected_media
            searcher.deduplicator.block_asset(child.selected_media.get('asset_id', ''))
        target.media_candidates = child.media_candidates
        if scene.visual_beats:
            target.search_attempts = searcher.search_attempts[attempt_start:]
            target.status = 'selected' if child.selected_media else 'pending_media'
            scene.selected_media = scene.visual_beats[0].selected_media
        if path.read_text(encoding='utf-8') != expected:
            raise RuntimeError('O projeto mudou durante a busca. Recarregue o Review Studio; a edição mais recente foi preservada.')
        expected = plan.to_json(indent=2)
        _atomic_write(path, expected)
        results.append({'scene': scene.scene_id, 'beat': key,
                        'status': 'selected_for_review' if child.selected_media else 'pending_media'})
        report = {'results': results, 'diagnosis': diagnosis(plan)}
        _atomic_write(path.parent/'recovery_report.json', json.dumps(report, ensure_ascii=False, indent=2))
    report = {'results': results, 'diagnosis': diagnosis(plan)}
    _atomic_write(path.parent/'recovery_report.json', json.dumps(report, ensure_ascii=False, indent=2))
    if progress:
        progress('Rodada concluída; confira as mídias encontradas.', 1.0)
    return report
