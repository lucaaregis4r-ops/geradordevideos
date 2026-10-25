from unittest.mock import Mock

import pytest

from app.services.audio import provider_retry as retry


def test_retries_server_delay_and_preserves_result(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(retry.time, 'sleep', sleep)
    progress = Mock()
    token = retry.retry_progress.set(progress)
    generate = Mock(side_effect=[RuntimeError("429 RESOURCE_EXHAUSTED {'retryDelay': '40s'}"), 'audio'])
    try:
        assert retry.generate_with_quota_retry(generate) == 'audio'
    finally:
        retry.retry_progress.reset(token)
    sleep.assert_called_once_with(42)
    assert generate.call_count == 2
    assert '42s' in progress.call_args.args[0]


@pytest.mark.parametrize('message', [
    '429 quota per day exhausted', '429 limit: 0',
    '429 Please retry in 3600s.',
])
def test_does_not_wait_for_unrecoverable_quota(monkeypatch, message):
    sleep = Mock()
    monkeypatch.setattr(retry.time, 'sleep', sleep)
    generate = Mock(side_effect=RuntimeError(message))
    with pytest.raises(retry.VoiceQuotaError, match='limite de uso'):
        retry.generate_with_quota_retry(generate)
    sleep.assert_not_called()
    assert generate.call_count == 1


def test_retry_budget_is_bounded(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(retry.time, 'sleep', sleep)
    generate = Mock(side_effect=RuntimeError('429 Please retry in 40.965457438s.'))
    with pytest.raises(retry.VoiceQuotaError):
        retry.generate_with_quota_retry(generate)
    assert generate.call_count == 4
    assert sleep.call_count == 3
    assert sum(c.args[0] for c in sleep.call_args_list) == 129


def test_non_quota_error_is_not_retried(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(retry.time, 'sleep', sleep)
    failure = ValueError('invalid voice')
    with pytest.raises(ValueError) as caught:
        retry.generate_with_quota_retry(Mock(side_effect=failure))
    assert caught.value is failure
    sleep.assert_not_called()


def test_quota_error_reaches_factory_caller(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from google import genai
    from app.services import voice

    generate = Mock(side_effect=RuntimeError('429 daily quota exhausted'))
    client = Mock()
    client.__enter__ = Mock(return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    client.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(genai, 'Client', Mock(return_value=client))
    monkeypatch.setitem(voice.config.app, 'gemini_api_key', 'test-key')
    output = tmp_path / 'scene_005.mp3'
    with pytest.raises(retry.VoiceQuotaError):
        voice.tts('Café.', 'gemini:Orus-Firm', 1.0, str(output))
    assert not output.exists()


def test_factory_does_not_master_missing_synthesis(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.services import factory as module

    factory = module.ShortsFactory.__new__(module.ShortsFactory)
    factory.voice_name = 'pt-BR-FranciscaNeural-Female'
    factory.projects_dir = tmp_path
    factory.searcher = Mock()
    factory.director = Mock()
    factory.director.direct_script.return_value = SimpleNamespace(scenes=[
        SimpleNamespace(scene_id='scene_005', narration='Café.')
    ])
    factory.pronunciation_engine = Mock()
    factory.pronunciation_engine.to_spoken.return_value = 'Café.'
    monkeypatch.setattr(module.voice, 'tts', Mock(return_value=None))
    master = Mock()
    monkeypatch.setattr(module, 'master_voice_track', master)
    with pytest.raises(RuntimeError, match='não gerou áudio para scene_005'):
        factory.produce_draft('test', 'Café.')
    master.assert_not_called()
    factory.searcher.populate_scene_plan.assert_not_called()
    assert retry.retry_progress.get() is None
