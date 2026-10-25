"""Explicitly reviewed assets enter a reusable library with their provenance."""
from pathlib import Path
from app.services.media_ranker.smart_library import SmartLibrary


def curate_asset(media: dict, description: str, tags: list[str], library_dir: Path):
    if media.get('semantic_status') not in {'reviewed', 'visual_verified'}:
        raise ValueError('Revise e aprove a pertinência da mídia antes de incluí-la no acervo.')
    if not media.get('rights_status') or media.get('rights_status', 'rights_unknown') in {'rights_unknown', 'blocked_for_this_use'}:
        raise ValueError('O registro precisa ter direitos de uso definidos antes de entrar no acervo.')
    if media.get('is_synthetic') or not Path(media.get('local_path') or '').is_file():
        raise ValueError('Escolha uma mídia real disponível localmente.')
    if not description.strip() or not any(t.strip() for t in tags):
        raise ValueError('Descreva o que aparece na mídia e informe ao menos uma etiqueta.')
    return SmartLibrary(library_dir).register_approved_asset(
        media['local_path'], [t.strip() for t in tags if t.strip()], intent=description.strip(),
        asset_id=media.get('asset_id'), duration=float(media.get('duration') or 0),
        metadata={k:media.get(k, '') for k in ('provider', 'source_page', 'creator_name',
                  'license_id', 'license_url', 'rights_status', 'perceptual_hash')})
