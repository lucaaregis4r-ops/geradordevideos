"""Bounded retries for temporary Gemini TTS quota limits."""
from __future__ import annotations

import math
import re
import time
from contextvars import ContextVar
from typing import Callable, TypeVar

from loguru import logger

T = TypeVar('T')
retry_progress: ContextVar[Callable[[str], None] | None] = ContextVar('tts_retry_progress', default=None)


class VoiceQuotaError(RuntimeError):
    """Safe, user-facing provider error (without credentials or response body)."""


def generate_with_quota_retry(generate: Callable[[], T]) -> T:
    waited = 0.0
    for attempt in range(4):
        try:
            return generate()
        except Exception as exc:
            message = str(exc)
            if getattr(exc, 'code', None) != 429 and not re.search(r'\b429\b|RESOURCE_EXHAUSTED', message):
                raise
            # A daily/exhausted quota cannot be repaired by a short wait.
            daily = re.search(r'per.?day|daily|limit:\s*0\b', message, re.I)
            match = re.search(r'retryDelay[\"\x27]?\s*:\s*[\"\x27]?(\d+(?:\.\d+)?)s', message)
            if not match:
                match = re.search(r'retry in (\d+(?:\.\d+)?)s', message, re.I)
            delay = math.ceil(float(match.group(1))) + 2 if match else 60
            if daily or attempt == 3 or delay > 120 or waited + delay > 180:
                raise VoiceQuotaError(
                    'O Gemini atingiu o limite de uso para geração de voz. '
                    'Tente novamente mais tarde ou confira a cota do projeto Gemini.'
                ) from exc
            notice = f'Limite temporário do Gemini: aguardando {delay}s para tentar a mesma cena novamente ({attempt + 1}/3).'
            logger.warning(notice)
            callback = retry_progress.get()
            if callback:
                callback(notice)
            time.sleep(delay)
            waited += delay
    raise AssertionError('unreachable')
