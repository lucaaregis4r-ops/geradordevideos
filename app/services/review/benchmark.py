"""Human-labelled retrieval benchmark. No inferred or auto-approved ratings."""
import json
from datetime import datetime, timezone
from pathlib import Path
import uuid

CASES_FILE = Path(__file__).resolve().parent / 'data/media_benchmark_30.json'


def load_cases() -> list[dict]:
    return json.loads(CASES_FILE.read_text(encoding='utf-8'))


def search_case(case_id: str, searcher) -> dict:
    from app.services.director.schemas import Scene
    case = next(c for c in load_cases() if c['id'] == case_id)
    searcher.reset()
    scene = Scene(case_id, case['brief'], case['brief'], case['queries'])
    found = searcher.search_for_scene(scene, target_duration=case['duration'], candidates_per_scene=5)
    return {'case': case, 'candidates': [c.to_dict() for c in found], 'attempts': searcher.search_attempts}


def record_rating(case_id: str, candidate: dict, *, reviewer: str, subject: bool,
                  action: bool, framing: bool, notes: str = '', root: Path = Path('storage/benchmark_ratings')) -> None:
    if case_id not in {c['id'] for c in load_cases()} or not reviewer.strip():
        raise ValueError('Informe um caso válido e o nome do avaliador.')
    if any(type(v) is not bool for v in (subject, action, framing)):
        raise ValueError('Avalie os três critérios antes de salvar.')
    if not candidate.get('asset_id') or not Path(candidate.get('local_path') or '').is_file():
        raise ValueError('Carregue e assista à mídia antes de avaliar.')
    case = next(c for c in load_cases() if c['id'] == case_id)
    row = {'brief':case['brief'], 'queries':case['queries'],
           'description':candidate.get('description', ''), 'source_page':candidate.get('source_page', ''),
           'case_id':case_id,'asset_id':candidate['asset_id'],'provider':candidate.get('provider'),
           'reviewer':reviewer.strip(),'subject':subject,'action':action,'framing':framing,
           'notes':notes,'created_at':datetime.now(timezone.utc).isoformat()}
    root.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    temporary = root/f'{token}.tmp'
    try:
        temporary.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(root/f'{token}.json')
    finally:
        temporary.unlink(missing_ok=True)


def summarize(root: Path = Path('storage/benchmark_ratings')) -> dict:
    # Last assessment per case/candidate/reviewer; keep immutable history on disk.
    latest = {}
    for p in root.glob('*.json'):
        row=json.loads(p.read_text(encoding='utf-8'))
        key=(row['case_id'],row['asset_id'],row['reviewer'])
        if key not in latest or row['created_at'] > latest[key]['created_at']:
            latest[key]=row
    rows=list(latest.values())
    return {'total_cases':len(load_cases()),'reviewed_cases':len({r['case_id'] for r in rows}),
            'ratings':len(rows),'accepted_ratings':sum(all(r[k] for k in ('subject','action','framing')) for r in rows),
            'results':rows}
