"""Persistent production jobs, guarded against simultaneous UI/worker execution."""
from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from uuid import uuid4

from app.services.audio.provider_retry import VoiceQuotaError


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


@contextmanager
def project_lock(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / '.production.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Esta produção já está em andamento.') from None
        yield


def has_quota_cause(exc: Exception) -> bool:
    while exc:
        if isinstance(exc, VoiceQuotaError):
            return True
        exc = exc.__cause__
    return False


def durable_production(fn):
    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        bound = inspect.signature(fn).bind(self, *args, **kwargs)
        bound.apply_defaults()
        params = {k: v for k, v in bound.arguments.items() if k not in ('self', 'on_progress')}
        params['voice_name'] = params['voice_name'] or self.voice_name
        if params.get('bgm_path'):
            params['bgm_path'] = str(params['bgm_path'])
        folder = self.projects_dir / params['script_id']
        if folder.resolve().parent != self.projects_dir.resolve():
            raise ValueError('Identificador de projeto inválido.')
        with project_lock(folder):
            path = folder / 'production_job.json'
            job = json.loads(path.read_text()) if path.exists() else {'params': params}
            if job['params'] != params:
                raise ValueError('Este projeto já tem um roteiro e configurações salvos. Crie outra produção para alterá-los.')
            if job.get('status') in ('completed', 'needs_review'):
                return job['result']
            job.update(status='running', updated_at=time.time())
            write_json(path, job)
            try:
                result = fn(self, *args, **kwargs)
            except Exception as exc:
                if has_quota_cause(exc):
                    job.update(status='waiting_quota', next_attempt_at=time.time() + 86400,
                               error='Cota de voz atingida. Retomada automática em 24 horas.')
                    write_json(path, job)
                    return {'script_id': params['script_id'], 'status': 'waiting_quota',
                            'video_path': None, 'error': job['error'], 'next_attempt_at': job['next_attempt_at']}
                job.update(status='failed', error=f'Falha de produção ({type(exc).__name__}). Consulte os logs locais.')
                write_json(path, job)
                raise
            job.update(status='completed' if result.get('video_path') else 'needs_review', result=result)
            write_json(path, job)
            return result
    return wrapped


def audio_signature(text: str, voice: str, rate: float) -> str:
    return hashlib.sha256(json.dumps([text, voice, rate], ensure_ascii=False).encode()).hexdigest()


def audio_cached(path: Path, signature: str) -> bool:
    receipt = path.with_suffix('.receipt.json')
    if not path.is_file() or not receipt.exists():
        return False
    try:
        saved = json.loads(receipt.read_text())
        return saved == {'signature': signature, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    except (ValueError, OSError):
        return False


def remember_audio(path: Path, signature: str) -> None:
    write_json(path.with_suffix('.receipt.json'),
               {'signature': signature, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})


def run_due(base_dir: Path, now: float | None = None, factory_builder=None) -> int:
    now = time.time() if now is None else now
    count = 0
    for path in sorted((base_dir / 'projects').glob('*/production_job.json')):
        try:
            job = json.loads(path.read_text())
            if job['status'] not in ('waiting_quota', 'running'):
                continue
            if job['status'] == 'waiting_quota' and job['next_attempt_at'] > now:
                continue
            if factory_builder is None:
                from app.services.factory import ShortsFactory
                factory_builder = ShortsFactory
            factory_builder(base_dir=base_dir).produce_draft(**job['params'])
            count += 1
        except Exception:
            from loguru import logger
            logger.exception('Não foi possível retomar {}', path.parent.name)
    return count


if __name__ == '__main__':
    run_due(Path('storage').resolve())
