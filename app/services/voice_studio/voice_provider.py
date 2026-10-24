"""Voice Provider abstraction for Fábrica de Shorts (Section 15).

Supports interchangeable TTS engines: EdgeVoice, GeminiVoice, FallbackVoice.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from app.services import voice as legacy_voice


class VoiceProvider(ABC):
    """Abstract interface for TTS voice engines."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_name: str,
        rate: float = 1.0,
        volume: float = 1.0,
        output_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        """Synthesizes text into audio and returns a metadata dictionary:
        {
            "audio_path": str,
            "duration": float,
            "subtitles": Optional[str],
            "provider": str,
            "voice_name": str,
        }
        """
        pass

    @abstractmethod
    def list_voices(self, locale_prefix: str = "pt-BR") -> List[Dict[str, Any]]:
        """Returns available voices matching locale."""
        pass


class EdgeVoiceProvider(VoiceProvider):
    """Microsoft Edge TTS provider (Free, High quality, No API key needed)."""

    def list_voices(self, locale_prefix: str = "pt-BR") -> List[Dict[str, Any]]:
        from .catalog import PORTUGUESE_VOICES
        return [{**v, "provider": "edge", "gender": v["id"].rsplit("-", 1)[-1]}
                for v in PORTUGUESE_VOICES if v["locale"].startswith(locale_prefix)]

    def synthesize(
        self,
        text: str,
        voice_name: str = "pt-BR-AntonioNeural-Male",
        rate: float = 1.0,
        volume: float = 1.0,
        output_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        if not output_path:
            fd, temp_file = tempfile.mkstemp(suffix=".mp3", prefix="edge_tts_")
            import os; os.close(fd)
            out_file = Path(temp_file)
        else:
            out_file = Path(output_path).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)

        from .catalog import validate_voice_configuration
        validate_voice_configuration(voice_name)
        # Call the existing battle-tested voice.tts from legacy service
        sub = legacy_voice.tts(
            text=text,
            voice_name=voice_name,
            voice_rate=float(rate),
            voice_file=str(out_file),
            voice_volume=float(volume),
        )

        if not out_file.is_file() or out_file.stat().st_size == 0:
            raise RuntimeError("O provedor não gerou áudio. Verifique chave, cota e disponibilidade da voz.")

        # Probe duration with ffprobe
        duration = 0.0
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(out_file),
            ]
            out = subprocess.check_output(cmd).decode().strip()
            duration = float(out)
        except Exception:
            pass

        return {
            "audio_path": str(out_file),
            "duration": round(duration, 2),
            "subtitles": str(sub) if sub else None,
            "provider": "gemini" if voice_name.startswith("gemini:") else "edge",
            "voice_name": voice_name,
        }


class FallbackVoiceProvider(VoiceProvider):
    """Deterministic synthetic voice generator using FFmpeg sine waves for unit testing."""

    def list_voices(self, locale_prefix: str = "pt-BR") -> List[Dict[str, Any]]:
        return [
            {
                "id": "fallback_test_voice",
                "name": "Voz de Teste Sintética",
                "gender": "Neutral",
                "locale": "pt-BR",
                "provider": "fallback",
            }
        ]

    def synthesize(
        self,
        text: str,
        voice_name: str = "fallback_test_voice",
        rate: float = 1.0,
        volume: float = 1.0,
        output_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        if not output_path:
            fd, temp_file = tempfile.mkstemp(suffix=".mp3", prefix="fallback_voice_")
            import os; os.close(fd)
            out_file = Path(temp_file)
        else:
            out_file = Path(output_path).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)

        words = len(text.split())
        duration = max(1.5, words * 0.4 / rate)

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-ar", "48000", "-ac", "2", "-c:a", "libmp3lame",
            str(out_file),
        ]
        subprocess.run(cmd, check=True)

        return {
            "audio_path": str(out_file),
            "duration": round(duration, 2),
            "subtitles": None,
            "provider": "fallback",
            "voice_name": voice_name,
        }
