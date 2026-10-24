"""Voice Studio — Fábrica de Shorts (Streamlit UI).

Interactive voice auditioning, phrase-by-phrase playback, and pronunciation dictionary management.
"""

from pathlib import Path
import streamlit as st

from app.services.voice_studio.voice_service import VoiceStudioService


st.set_page_config(
    page_title="Voice Studio — Fábrica de Shorts",
    page_icon="🎙️",
    layout="wide",
)

st.title("🎙️ Voice Studio — Fábrica de Shorts")
st.caption("Ajuste vozes em português natural, teste qualquer frase instantaneamente sem renderizar vídeo e controle o dicionário fonético.")

voice_service = VoiceStudioService()
from app.services.voice_studio.catalog import production_voices
available_voices = production_voices()

tab_audition, tab_dict = st.tabs(["🔊 Teste de Voz (Instant Preview)", "📖 Dicionário de Pronúncia"])

with tab_audition:
    st.subheader("Testar Voz Frase a Frase")
    st.caption("Ouça exatamente como a narração soará antes de aplicar ao projeto.")

    col_cfg1, col_cfg2, col_cfg3 = st.columns([1.2, 1.2, 1])

    with col_cfg1:
        provider_name = st.selectbox(
            "Provedor de Voz:",
            ["Edge TTS (Gratuito - Microsoft Neural)", "Gemini (API configurada)"],
            index=0,
        )

    with col_cfg2:
        available_voices = [v for v in available_voices if v['provider'] == ('gemini' if provider_name.startswith('Gemini') else 'edge')]
        voice_labels = [v['name'] for v in available_voices]
        selected_label = st.selectbox(
            "Voz em Português:",
            voice_labels,
            index=0,
        )
        selected_voice_obj = next(v for v in available_voices if v["name"] == selected_label)
        selected_voice_id = selected_voice_obj["id"]

    with col_cfg3:
        speed_rate = st.slider(
            "Velocidade (Rate):",
            min_value=0.80,
            max_value=1.50,
            value=1.00,
            step=0.05,
            format="%.2fx",
            disabled=provider_name.startswith("Gemini"),
        )

    test_phrase = st.text_area(
        "Texto para Audicão:",
        value="Você provavelmente aprendeu que força é massa vezes aceleração, onde F = m.a. Mas empurrar um carrinho cheio é outra história!",
        height=100,
    )

    col_btn, col_check = st.columns([1, 2])
    with col_check:
        apply_dict = st.checkbox("Aplicar Dicionário Fonético de Pronúncia", value=True)

    with col_btn:
        btn_preview = st.button("▶ Ouvir Frase Instantaneamente", type="primary", use_container_width=True)

    if btn_preview:
        with st.spinner("Sintetizando áudio com o provedor selecionado..."):
            try:
                res = voice_service.preview_phrase(
                    text=test_phrase,
                    voice_name=selected_voice_id,
                    rate=1.0 if provider_name.startswith("Gemini") else speed_rate,
                    apply_pronunciation=apply_dict,
                )
                audio_path = res["audio_path"]

                st.success(f"Áudio gerado em {res['duration']}s!")
                st.audio(audio_path, format="audio/mp3")

                # Comparison cards
                c_disp, c_spok = st.columns(2)
                with c_disp:
                    st.markdown("**📝 Texto da Legenda (Visual Display):**")
                    st.info(res["display_text"])
                with c_spok:
                    st.markdown("**🗣️ Texto Falado pelo TTS (Fonético):**")
                    st.info(res["spoken_text"])

            except Exception as e:
                st.error(f"Erro na síntese de voz: {e}")

with tab_dict:
    st.subheader("Dicionário Fonético de Pronúncia")
    st.caption("Substitui siglas, fórmulas ou termos estrangeiros no áudio falado sem alterar a legenda aprovada na tela.")

    # Add Rule Form
    with st.expander("➕ Adicionar Nova Regra de Pronúncia", expanded=True):
        with st.form("form_add_rule"):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                term_input = st.text_input("Termo Escrito (ex: E = mc², NASA, km/h):", placeholder="Ex: F = m.a")
            with col_t2:
                spoken_input = st.text_input("Como deve ser falado (fonético):", placeholder="Ex: Éfe é igual a ême vezes á")

            submitted = st.form_submit_button("Salvar Regra")
            if submitted:
                if term_input and spoken_input:
                    voice_service.add_pronunciation_rule(term_input, spoken_input)
                    st.success(f"Regra '{term_input}' -> '{spoken_input}' adicionada com sucesso!")
                    st.rerun()
                else:
                    st.warning("Preencha ambos os campos para salvar a regra.")

    # Current Rules List
    st.markdown("#### Regras Ativas no Sistema")
    current_rules = voice_service.get_pronunciation_rules()

    if current_rules:
        for term, spoken in sorted(current_rules.items()):
            col_r1, col_r2, col_r3 = st.columns([1.5, 2.5, 0.8])
            with col_r1:
                st.code(term, language=None)
            with col_r2:
                st.write(f"➔ **{spoken}**")
            with col_r3:
                if st.button("🗑️ Excluir", key=f"del_{term}"):
                    voice_service.remove_pronunciation_rule(term)
                    st.rerun()
    else:
        st.info("Nenhuma regra personalizada configurada.")
