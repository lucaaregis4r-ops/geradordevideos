"""Portuguese Edge voices verified against the live catalog on 2026-10-24."""
PORTUGUESE_VOICES = [
    {'id': 'pt-BR-FranciscaNeural-Female', 'name': 'Francisca — Brasil', 'locale': 'pt-BR'},
    {'id': 'pt-BR-AntonioNeural-Male', 'name': 'Antônio — Brasil', 'locale': 'pt-BR'},
    {'id': 'pt-BR-ThalitaMultilingualNeural-Female', 'name': 'Thalita — Brasil, multilíngue', 'locale': 'pt-BR'},
    {'id': 'pt-PT-DuarteNeural-Male', 'name': 'Duarte — Portugal', 'locale': 'pt-PT'},
    {'id': 'pt-PT-RaquelNeural-Female', 'name': 'Raquel — Portugal', 'locale': 'pt-PT'},
]


def production_voices() -> list[dict]:
    from app.services.voice import GEMINI_TTS_VOICES
    return [dict(v, provider='edge') for v in PORTUGUESE_VOICES] + [
        {'id': f'gemini:{name}-{style}', 'name': f'Gemini · {name} ({style})',
         'locale': 'multilingual', 'provider': 'gemini'} for name, style in GEMINI_TTS_VOICES
    ]


def validate_voice_configuration(voice_id: str) -> None:
    if voice_id.startswith('gemini:'):
        from app.config import config
        if not config.app.get('gemini_api_key'):
            raise ValueError('Configure a chave Gemini nas configurações de TTS da página principal antes de usar esta voz.')
