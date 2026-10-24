"""Brand kit editor for future productions; existing projects retain their snapshot."""
import hashlib
from pathlib import Path
import streamlit as st
from app.services.branding.kit import BrandKit, load_kit, save_kit
from app.services.voice_studio.catalog import production_voices
from app.services.graphics.typography_engine import TypographyEngine

st.set_page_config(page_title='Identidade da Fábrica', page_icon='🎨', layout='wide')
st.title('🎨 Identidade da produção')
st.caption('Salve cores, voz e trilha para aplicar às próximas produções. Cada projeto guarda sua própria cópia do kit.')
kit = load_kit()
name = st.text_input('Nome da identidade', kit.name)
accent = st.color_picker('Cor de destaque dos textos', kit.accent)
st.image(TypographyEngine(accent=accent).render_overlay('QUEM FEZ ISSO?', level='title'), width=270)
voices = {v['id']: v['name'] for v in production_voices()}
selected = st.selectbox('Voz', list(voices), index=list(voices).index(kit.voice) if kit.voice in voices else 0, format_func=voices.get)
is_gemini = selected.startswith('gemini:')
rate = st.slider('Velocidade da fala', 0.8, 1.3, 1.0 if is_gemini else kit.voice_rate, 0.05, disabled=is_gemini)
if is_gemini:
    st.caption('Gemini usa a chave já configurada no programa e consome sua cota de API. O controle de velocidade deste motor ainda não é aplicado.')
phrase = st.text_input('Frase para ouvir', 'Por trás de cada produto, existe uma história que merece ser contada.')
if st.button('Ouvir esta voz'):
    from app.services.voice_studio.voice_service import VoiceStudioService
    try:
        with st.spinner('Gerando amostra…'):
            result = VoiceStudioService().preview_phrase(phrase, voice_name=selected, rate=rate)
        st.audio(result['audio_path'])
    except Exception as exc:
        st.error(f'Não foi possível gerar a amostra: {type(exc).__name__}. Tente novamente.')

upload = st.file_uploader('Trilha musical que você pode usar', type=['mp3', 'wav', 'ogg', 'm4a'])
remove = st.checkbox('Produzir sem trilha musical', value=not bool(kit.music_path))
volume = st.slider('Volume base da trilha', 0.0, 0.3, kit.music_volume, 0.01)
st.caption('A música abaixa automaticamente durante a fala. Desmarque “sem trilha” para aplicar o arquivo enviado.')
if kit.music_path and Path(kit.music_path).is_file():
    st.audio(kit.music_path)
if st.button('Salvar identidade', type='primary'):
    music = kit.music_path
    if upload and not remove:
        data = upload.getvalue()
        path = Path('storage/brand_music') / (hashlib.sha256(data).hexdigest() + Path(upload.name).suffix.lower())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        music = str(path.resolve())
    save_kit(BrandKit(name=name, accent=accent, voice=selected, voice_rate=rate,
                     music_path='' if remove else music, music_volume=volume))
    st.success('Identidade salva. Na página principal, ative “Aplicar identidade salva”.')
