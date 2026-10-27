"""Brand kit editor for future productions; existing projects retain their snapshot."""
import hashlib
from pathlib import Path
import streamlit as st
from app.services.branding.kit import BrandKit, load_kit, save_kit
from app.services.branding.library import list_presets, save_preset, preset_label
from app.services.branding.looks import LOOK_LABELS, VisualLook, render_look
from app.services.voice_studio.catalog import production_voices
from app.services.graphics.typography_engine import TypographyEngine

st.set_page_config(page_title='Identidade da Fábrica', page_icon='🎨', layout='wide')
st.title('🎨 Identidade da produção')
st.caption('Salve filtros de imagem, cores, voz e trilha para aplicar às próximas produções. Cada projeto guarda sua própria cópia do kit.')
presets = list_presets()
choice = st.selectbox('Preset para editar', ['new', 'legacy', *presets],
    format_func=lambda key: {'new': 'Criar novo preset', 'legacy': 'Importar identidade anterior'}.get(key) or preset_label(presets[key]))
kit = presets[choice] if choice in presets else load_kit() if choice == 'legacy' else BrandKit()
channel = st.text_input('Canal', kit.channel, help='Exemplo: Mercadoria, Ciência em Minutos ou Histórias do Trabalho.')
name = st.text_input('Nome da identidade', kit.name)
st.subheader('Tratamento das imagens')
preset = st.selectbox('Estilo de imagem', list(LOOK_LABELS),
                      index=list(LOOK_LABELS).index(kit.look.preset), format_func=LOOK_LABELS.get)
intensity = st.slider('Intensidade do estilo', 0.0, 1.0, kit.look.intensity, 0.05)
grain = st.slider('Granulação suave', 0.0, 1.0, kit.look.grain, 0.05)
vignette = st.slider('Escurecimento suave das bordas', 0.0, 1.0, kit.look.vignette, 0.05)
look = VisualLook(preset=preset, intensity=intensity, grain=grain, vignette=vignette)
st.caption('O mesmo tratamento será aplicado aos vídeos e fotos animadas, antes dos textos. Granulação e bordas são ajustes independentes do estilo.')
with st.expander('Comparar antes e depois em um trecho de 3 segundos'):
    sample = st.file_uploader('Vídeo para testar o tratamento', type=['mp4', 'mov', 'webm'], key='look_sample')
    preview_start = st.number_input('Início do trecho (segundos)', min_value=0.0, value=0.0, step=1.0)
    if st.button('Gerar comparação', disabled=sample is None):
        data = sample.getvalue()
        sample_path = Path('storage/look_previews') / (hashlib.sha256(data).hexdigest() + Path(sample.name).suffix.lower())
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(data)
        try:
            with st.spinner('Aplicando o tratamento ao trecho…'):
                before = render_look(sample_path, VisualLook(), sample_path.parent, source_in=preview_start, duration=3, preview=True)
                after = render_look(sample_path, look, sample_path.parent, source_in=preview_start, duration=3, preview=True)
            st.session_state['look_comparison'] = (str(before), str(after), look.model_dump(), preview_start)
        except Exception:
            st.error('Não foi possível processar o trecho. Use um vídeo legível com pelo menos 3 segundos após o ponto escolhido.')
    comparison = st.session_state.get('look_comparison')
    if comparison:
        if comparison[2] != look.model_dump() or comparison[3] != preview_start:
            st.info('Os ajustes mudaram. Gere outra comparação para atualizar a prévia.')
        left, right = st.columns(2)
        with left:
            st.caption('Antes — trecho original, sem áudio')
            st.video(comparison[0])
        with right:
            st.caption('Depois — tratamento aplicado, sem áudio')
            st.video(comparison[1])
st.subheader('Textos e som')
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

upload = st.file_uploader('Trilha musical que você pode usar', type=['mp3', 'wav', 'ogg', 'm4a'], key=f'music_{choice}')
remove = st.checkbox('Produzir sem trilha musical', value=not bool(kit.music_path))
volume = st.slider('Volume base da trilha', 0.0, 0.3, kit.music_volume, 0.01)
st.caption('A música abaixa automaticamente durante a fala. Desmarque “sem trilha” para aplicar o arquivo enviado.')
if kit.music_path and Path(kit.music_path).is_file():
    st.audio(kit.music_path)
save_copy = st.checkbox('Salvar como novo preset (preservar o original)', value=choice not in presets)
if st.button('Salvar preset', type='primary'):
    music = kit.music_path
    if upload and not remove:
        data = upload.getvalue()
        path = Path('storage/brand_music') / (hashlib.sha256(data).hexdigest() + Path(upload.name).suffix.lower())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        music = str(path.resolve())
    updated = BrandKit(name=name, channel=channel, accent=accent, voice=selected, voice_rate=rate, look=look,
                       music_path='' if remove else music, music_volume=volume)
    save_preset(updated, None if save_copy or choice not in presets else choice)
    st.success('Preset salvo. Na página principal, ative “Aplicar identidade salva” e selecione este canal/preset.')
