import json
from pathlib import Path

import pytest

from app.services.production import resume as r
from app.services.audio.provider_retry import VoiceQuotaError


class Factory:
    def __init__(self, base_dir):
        self.projects_dir = Path(base_dir) / 'projects'
        self.voice_name = 'test'
        self.calls = 0

    @r.durable_production
    def produce_draft(self, script_id, script_text, voice_name=None, bgm_path=None, on_progress=None):
        self.calls += 1
        if self.calls == 1:
            try:
                raise VoiceQuotaError('quota')
            except VoiceQuotaError as exc:
                raise RuntimeError('scene') from exc
        return {'video_path': 'finished.mp4'}


def test_schedule_then_resume_after_24h(tmp_path, monkeypatch):
    monkeypatch.setattr(r.time, 'time', lambda: 100)
    f = Factory(tmp_path)
    result = f.produce_draft('p', 'literal')
    assert result['status'] == 'waiting_quota'
    assert result['next_attempt_at'] == 86500
    assert r.run_due(tmp_path, now=86499, factory_builder=lambda **kw: f) == 0
    assert f.calls == 1
    assert r.run_due(tmp_path, now=86500, factory_builder=lambda **kw: f) == 1
    assert f.calls == 2
    assert json.loads((tmp_path/'projects/p/production_job.json').read_text())['status'] == 'completed'
    assert f.produce_draft('p', 'literal')['video_path']
    assert f.calls == 2


def test_changed_input_does_not_reuse_old_job(tmp_path):
    f = Factory(tmp_path)
    f.produce_draft('p', 'original')
    with pytest.raises(ValueError):
        f.produce_draft('p', 'modified')


def test_lock_prevents_duplicate_execution(tmp_path):
    f = Factory(tmp_path)
    with r.project_lock(tmp_path/'projects/p'):
        with pytest.raises(RuntimeError, match='andamento'):
            f.produce_draft('p', 'text')
    assert f.calls == 0


def test_audio_receipt_detects_corruption_and_different_voice(tmp_path):
    p = tmp_path/'voice.mp3'
    p.write_bytes(b'audio')
    sig = r.audio_signature('literal', 'Fenrir', 1.0)
    assert not r.audio_cached(p, sig)
    r.remember_audio(p, sig)
    assert r.audio_cached(p, sig)
    assert not r.audio_cached(p, r.audio_signature('literal', 'Orus', 1.0))
    p.write_bytes(b'broken')
    assert not r.audio_cached(p, sig)


def test_cancelled_job_not_dispatched(tmp_path):
    f = Factory(tmp_path)
    f.produce_draft('p', 'text')
    p = tmp_path/'projects/p/production_job.json'
    job = json.loads(p.read_text())
    job['status'] = 'cancelled'
    r.write_json(p, job)
    assert r.run_due(tmp_path, now=10**12, factory_builder=lambda **kw: f) == 0


def test_factory_resumes_only_missing_voice_and_reuses_plan(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from app.services import factory as m
    from app.services.director.schemas import Scene, ScenePlan
    f = m.ShortsFactory.__new__(m.ShortsFactory)
    f.projects_dir = tmp_path/'projects'
    f.voice_name = 'pt-BR-FranciscaNeural-Female'
    f.searcher = Mock()
    f.searcher.populate_scene_plan.side_effect = RuntimeError('stop before media')
    f.director = Mock()
    f.director.direct_script.return_value = ScenePlan('p', 'v1', 'hash', 2, 4, [
        Scene('s1', 'First.', 'cup', ['coffee cup']), Scene('s2', 'Second.', 'cup', ['coffee cup'])])
    f.pronunciation_engine = Mock()
    f.pronunciation_engine.to_spoken.side_effect = lambda text: text
    calls = []
    def tts(**kw):
        calls.append(kw['text'])
        if len(calls) == 2:
            raise VoiceQuotaError('quota')
        Path(kw['voice_file']).write_bytes(b'audio')
    monkeypatch.setattr(m.voice, 'tts', tts)
    monkeypatch.setattr(m, '_measure_audio_duration', lambda path: 2)
    monkeypatch.setattr(m, 'master_voice_track', lambda src, dst, **kw: dst.write_bytes(b'mastered'))
    assert f.produce_draft('p', 'First. Second.')['status'] == 'waiting_quota'
    with pytest.raises(RuntimeError, match='stop before media'):
        f.produce_draft('p', 'First. Second.')
    assert calls == ['First.', 'Second.', 'Second.']
    assert f.director.direct_script.call_count == 1
