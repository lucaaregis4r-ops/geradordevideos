"""Review Studio — Fábrica de Shorts / Projeto Mercadoria (Streamlit UI).

Interface editorial em duas etapas:
- Etapa 1: Direção e Decupagem de Cenas, Beats e Queries concretas (antes do render).
- Etapa 2: Storyboard Visual, Troca de Mídias com 1 Clique, Quality Gate ao Vivo e Render Final.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import streamlit as st

from app.services.director.presets import list_presets, get_preset
from app.services.review.review_manager import ReviewManager


st.set_page_config(
    page_title="Review Studio — Fábrica de Shorts",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for polished editorial styling
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #1A1D24;
        border: 1px solid #2E3440;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 10px;
    }
    .badge-approved {
        background-color: #10B981;
        color: white;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-rejected {
        background-color: #EF4444;
        color: white;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 1.05rem;
        font-weight: 600;
        padding: 8px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

manager = ReviewManager()
all_presets = list_presets()
preset_names = [p.name for p in all_presets]

# --- SIDEBAR: Project Selection & Actions ---
with st.sidebar:
    st.title("🎬 Review Studio")
    st.caption("Fábrica Editorial de Ensaios Verticais 9:16")
    st.divider()

    projects_summary = manager.list_projects_summary()
    project_ids = [p["project_id"] for p in projects_summary]

    mode = st.radio(
        "Modo de Operação:",
        ["📁 Produções Existentes", "✨ Nova Produção"],
        index=0 if project_ids else 1,
    )

    selected_project_id = None
    if mode == "📁 Produções Existentes" and project_ids:
        selected_project_id = st.selectbox(
            "Selecione o Projeto:",
            project_ids,
            index=0,
        )
        if st.button("🔄 Atualizar Lista", use_container_width=True):
            st.rerun()
    elif mode == "📁 Produções Existentes":
        st.info("Nenhuma produção encontrada. Crie uma nova na aba 'Nova Produção'.")

# --- MAIN SCREEN ROUTING ---

if mode == "✨ Nova Produção":
    st.header("✨ Iniciar Nova Produção Editorial (Etapa 1)")
    st.caption("Insira o roteiro humano aprovado, configure o preset visual e realize a decupagem de cenas.")

    col1, col2 = st.columns([1.2, 1])
    with col1:
        new_project_id = st.text_input(
            "ID do Projeto (slug único):",
            value="ensaio_mercadoria_01",
            help="Nome da pasta sem espaços ou caracteres especiais.",
        )
        new_title = st.text_input("Título do Episódio:", value="O Fetiche da Mercadoria no Cotidiano")
        new_channel = st.text_input("Canal / Marca:", value="projeto_mercadoria")

        chosen_preset = st.selectbox(
            "Preset Editorial de Direção:",
            preset_names,
            index=0,
            format_func=lambda n: f"{get_preset(n).display_title} ({n})",
        )

        preset_info = get_preset(chosen_preset)
        st.info(f"**{preset_info.display_title}**\n\n{preset_info.description}\n\n"
                f"• Cadência: {preset_info.target_pace_seconds[0]}s a {preset_info.target_pace_seconds[1]}s por cena\n"
                f"• Fases Narrativas: `{' → '.join(preset_info.allowed_phases)}`\n"
                f"• Componentes Permitidos: `{'`, `'.join(preset_info.preferred_components)}`")

    with col2:
        new_script_text = st.text_area(
            "Roteiro Falado Aprovado (Human Script):",
            height=320,
            value=(
                "Quer entender como a economia funciona de verdade?\n"
                "Começa com uma caneca de vinte reais.\n"
                "O preço de uma camiseta na vitrine custa R$ 89 reais, mas o custo real de produção na fábrica é de apenas R$ 12 reais.\n"
                "Quem pagou a diferença foi o trabalho invisível de quem costurou."
            ),
            help="O texto falado é estritamente sagrado: a narração será decupada sem alterações.",
        )

        if st.button("🎬 Decupar Roteiro (Scene Director)", type="primary", use_container_width=True):
            with st.spinner("Decupando roteiro em cenas e visual beats com o Scene Director..."):
                try:
                    res = manager.direct_script(
                        script_id=new_project_id.strip(),
                        script_text=new_script_text.strip(),
                        title=new_title.strip(),
                        channel=new_channel.strip(),
                        brand_preset=chosen_preset,
                    )
                    st.success(f"Decupagem concluída com sucesso! {res['total_scenes']} cenas geradas.")
                    st.session_state["active_project"] = new_project_id.strip()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro na decupagem: {exc}")

elif selected_project_id:
    # Load selected project data
    try:
        project_data = manager.get_project_data(selected_project_id)
    except Exception as exc:
        st.error(f"Erro ao carregar dados do projeto '{selected_project_id}': {exc}")
        st.stop()

    plan = project_data["plan"]
    latest_video = project_data["latest_video"]
    current_rev = project_data["current_revision"]

    # Header and Top Metrics
    st.title(f"🎬 {getattr(plan, 'title', selected_project_id)}")
    st.caption(f"Projeto: `{selected_project_id}` | Preset: `{plan.brand_preset}` | Criado em: `{getattr(plan, 'created_at', 'N/A')[:19]}`")

    # 3 Workflow Tabs
    tab1, tab2, tab3 = st.tabs([
        "📝 Etapa 1: Roteiro & Decupagem",
        "🎞️ Etapa 2: Storyboard & Mídias",
        "📱 Etapa 3: Rascunho & Render Final",
    ])

    # =========================================================================
    # TAB 1: ROTEIRO & DECUPAGEM (ETAPA 1)
    # =========================================================================
    with tab1:
        st.subheader("📝 Decupagem Editorial e Queries Concretas")
        st.caption("Revise a segmentação das cenas antes de buscar mídias pesadas. A narração é protegida contra modificações.")

        t1_col1, t1_col2, t1_col3, t1_col4 = st.columns(4)
        with t1_col1:
            st.metric("Total de Cenas", len(plan.scenes))
        with t1_col2:
            st.metric("Duração Estimada", f"{plan.estimated_duration:.1f}s")
        with t1_col3:
            total_beats = sum(len(s.visual_beats) if s.has_multiple_beats else 1 for s in plan.scenes)
            st.metric("Total de Planos (Beats)", total_beats)
        with t1_col4:
            st.metric("Estilo Visual", plan.brand_preset.upper())

        st.divider()

        for idx, scene in enumerate(plan.scenes):
            with st.expander(
                f"**Cena #{idx+1}** (`{scene.scene_id}`) | Fase: `{scene.narrative_phase}` | Duração: `{scene.duration_hint:.1f}s`"
                + (f" | ⚡ Multi-Planos ({len(scene.visual_beats)} beats)" if scene.has_multiple_beats else ""),
                expanded=(idx == 0),
            ):
                # Narration: Sacred and Immutable
                st.markdown("**🗣️ Narração Falada (Texto Bloqueado - Regra de Ouro #1):**")
                st.info(f"🔒 \"{scene.narration}\"")

                col_sc1, col_sc2 = st.columns(2)
                with col_sc1:
                    new_intent = st.text_input(
                        "Intenção Visual da Cena:",
                        value=scene.intent,
                        key=f"intent_{scene.scene_id}",
                    )
                    queries_text = st.text_area(
                        "Queries Concretas em Inglês (uma por linha):",
                        value="\n".join(scene.queries),
                        key=f"queries_{scene.scene_id}",
                        help="NUNCA use termos conceituais (ex: 'economy', 'market'). Use apenas objetos físicos e ações tangíveis.",
                    )
                with col_sc2:
                    new_vtype = st.selectbox(
                        "Tipo Visual Base:",
                        ["stock_video", "stock_image", "graphic", "component"],
                        index=["stock_video", "stock_image", "graphic", "component"].index(scene.visual_type)
                        if scene.visual_type in ["stock_video", "stock_image", "graphic", "component"] else 0,
                        key=f"vtype_{scene.scene_id}",
                    )
                    new_motion = st.selectbox(
                        "Movimento de Câmera:",
                        ["lateral", "zoom_in", "zoom_out", "static"],
                        index=["lateral", "zoom_in", "zoom_out", "static"].index(scene.preferred_motion)
                        if scene.preferred_motion in ["lateral", "zoom_in", "zoom_out", "static"] else 0,
                        key=f"motion_{scene.scene_id}",
                    )
                    c_txt1, c_txt2 = st.columns(2)
                    with c_txt1:
                        new_overlay = st.text_input(
                            "Texto na Tela (Safe Area):",
                            value=scene.text_overlay or "",
                            key=f"overlay_{scene.scene_id}",
                        )
                    with c_txt2:
                        new_level = st.selectbox(
                            "Nível Tipográfico:",
                            ["title", "emphasis", "caption"],
                            index=["title", "emphasis", "caption"].index(scene.text_level)
                            if scene.text_level in ["title", "emphasis", "caption"] else 2,
                            key=f"level_{scene.scene_id}",
                        )

                # Visual Beats Inspection
                if scene.has_multiple_beats:
                    st.markdown("##### ⚡ Visual Beats (Multi-Planos dentro desta Cena):")
                    for b_idx, beat in enumerate(scene.visual_beats):
                        b_col1, b_col2, b_col3 = st.columns([1.5, 1.5, 1])
                        with b_col1:
                            st.caption(f"**Beat `{beat.beat_id}`** (Duração: {beat.duration:.1f}s)")
                            beat_q = st.text_input(
                                f"Queries Beat {beat.beat_id}:",
                                value=", ".join(beat.queries),
                                key=f"beat_q_{beat.beat_id}",
                            )
                        with b_col2:
                            beat_comp = st.selectbox(
                                f"Componente Beat {beat.beat_id}:",
                                ["nenhum", "price_tag", "split_screen", "historical_archive", "data_card", "editorial_crop"],
                                index=["nenhum", "price_tag", "split_screen", "historical_archive", "data_card", "editorial_crop"].index(beat.component_type)
                                if beat.component_type in ["price_tag", "split_screen", "historical_archive", "data_card", "editorial_crop"] else 0,
                                key=f"beat_comp_{beat.beat_id}",
                            )
                        with b_col3:
                            beat_overlay = st.text_input(
                                f"Texto Beat {beat.beat_id}:",
                                value=beat.text_overlay or "",
                                key=f"beat_txt_{beat.beat_id}",
                            )

                # Action button per scene
                if st.button(f"💾 Salvar Ajustes da Cena {idx+1}", key=f"save_sc_{scene.scene_id}"):
                    q_list = [q.strip() for q in queries_text.split("\n") if q.strip()]
                    manager.update_scene_metadata(
                        project_id=selected_project_id,
                        scene_id=scene.scene_id,
                        queries=q_list,
                        visual_type=new_vtype,
                        preferred_motion=new_motion,
                        text_overlay=new_overlay,
                        text_level=new_level,
                        intent=new_intent,
                    )
                    st.success(f"Cena {scene.scene_id} atualizada!")
                    st.rerun()

        st.divider()
        if st.button("🚀 Aprovar Decupagem e Buscar Mídias para Todas as Cenas", type="primary", use_container_width=True):
            with st.spinner("Buscando candidatos nas fontes (Pexels, Wikimedia, Openverse, Acervo)..."):
                manager.search_media_for_all_scenes(selected_project_id, candidates_per_scene=5)
                st.success("Busca de candidatos finalizada! Siga para a Etapa 2.")
                st.rerun()

    # =========================================================================
    # TAB 2: STORYBOARD & SELEÇÃO VISUAL (ETAPA 2)
    # =========================================================================
    with tab2:
        st.subheader("🎞️ Storyboard Visual, Troca de Mídias e Quality Gate ao Vivo")

        # Evaluate Quality Gate live
        qa_data = manager.evaluate_project_quality(selected_project_id)
        q_score = qa_data["quality_score"]

        # Quality Gate Hero Card
        q_passed = q_score.get("passed", False)
        status_color = "#10B981" if q_passed else "#EF4444"
        status_text = "🟢 QUALITY GATE: APROVADO PARA RENDER" if q_passed else "🔴 QUALITY GATE: REPROVADO (AJUSTES NECESSÁRIOS)"

        st.markdown(
            f"""
            <div style="background-color: #11141B; border-left: 6px solid {status_color}; padding: 14px 20px; border-radius: 6px; margin-bottom: 20px;">
                <h4 style="margin: 0; color: {status_color};">{status_text}</h4>
                <p style="margin: 4px 0 0 0; color: #94A3B8; font-size: 0.95rem;">
                    Pontuação Semântica Média: <b>{q_score.get('semantic_match_avg', 0.0):.2f}</b> (Mín 0.60) |
                    Diversidade Visual: <b>{q_score.get('visual_diversity', 0.0):.2f}</b> (Mín 0.30) |
                    Repetições: <b>{q_score.get('duplicate_assets', 0)}</b> |
                    Erros de Safe Area: <b>{q_score.get('text_safe_area_errors', 0)}</b>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if qa_data["alerts"]:
            with st.expander("⚠️ Alertas do Quality Gate (Clique para ver detalhes)", expanded=not q_passed):
                for alert in qa_data["alerts"]:
                    st.warning(f"• {alert}")

        st.divider()

        # Scene by Scene Storyboard and Candidate Swapping
        for idx, scene in enumerate(plan.scenes):
            with st.expander(f"🎬 **Cena {idx+1}** (`{scene.scene_id}`) — \"{scene.narration[:45]}...\"", expanded=(idx < 2)):
                col_sel, col_cands = st.columns([1, 2])

                # Active Media Viewer
                with col_sel:
                    st.markdown("**⭐ Mídia Selecionada (Ativa):**")
                    selected = scene.selected_media or {}
                    local_p = selected.get("local_path")
                    cand_type = selected.get("type", scene.visual_type)
                    provider = selected.get("provider", "local")

                    st.caption(f"Tipo: `{cand_type}` | Fonte: `{provider}` | Score: `{selected.get('final_score', 1.0):.2f}`")

                    if local_p and Path(local_p).exists():
                        if str(local_p).lower().endswith((".mp4", ".mov", ".avi")):
                            st.video(local_p)
                        else:
                            st.image(local_p, use_container_width=True)
                    else:
                        st.info("Nenhuma mídia baixada ainda para esta cena.")

                    if selected.get("author"):
                        st.caption(f"👤 Autor: {selected.get('author')} | Licença: {selected.get('license', 'Livre')}")

                    # Regenerate candidates button
                    if st.button(f"🔍 Re-buscar Candidatos da Cena {idx+1}", key=f"re_search_{scene.scene_id}"):
                        with st.spinner("Buscando novos candidatos nas fontes..."):
                            manager.search_media_for_scene(selected_project_id, scene.scene_id)
                            st.success("Novos candidatos encontrados!")
                            st.rerun()

                # Candidate Alternatives Grid
                with col_cands:
                    st.markdown("**🎞️ Candidatos Disponíveis para Troca Rápida (1-Clique):**")
                    candidates = scene.media_candidates or []
                    if candidates:
                        cols = st.columns(min(3, len(candidates)))
                        for c_idx, cand in enumerate(candidates[:3]):
                            with cols[c_idx]:
                                is_active = (selected.get("asset_id") == cand.get("asset_id")) or (selected.get("url") == cand.get("url"))
                                st.markdown(f"**Opção #{c_idx+1}**")
                                st.caption(f"Score: `{cand.get('final_score', cand.get('technical_score', 0.8)):.2f}` | Fonte: `{cand.get('provider', 'web')}`")

                                thumb_url = cand.get("thumbnail") or cand.get("url")
                                c_local = cand.get("local_path")
                                if c_local and Path(c_local).exists():
                                    if str(c_local).lower().endswith((".mp4", ".mov")):
                                        st.video(c_local)
                                    else:
                                        st.image(c_local, use_container_width=True)
                                elif thumb_url:
                                    st.image(thumb_url, use_container_width=True)

                                if is_active:
                                    st.button("✓ Selecionado", key=f"active_{scene.scene_id}_{c_idx}", disabled=True, use_container_width=True)
                                else:
                                    if st.button("🔄 Trocar para Este", key=f"swap_{scene.scene_id}_{c_idx}", use_container_width=True):
                                        with st.spinner("Substituindo mídia..."):
                                            target_path = cand.get("local_path")
                                            if not target_path or not Path(target_path).exists():
                                                from app.services.media_ranker.candidate_builder import _generate_synthetic_clip
                                                gen_p = Path(f"storage/media_cache/swap_{scene.scene_id}_{c_idx}.mp4")
                                                _generate_synthetic_clip(cand.get("query", scene.narration), gen_p)
                                                target_path = str(gen_p)

                                            manager.swap_scene_media(
                                                project_id=selected_project_id,
                                                scene_id=scene.scene_id,
                                                new_footage_path=target_path,
                                                new_candidate_info=cand,
                                            )
                                            st.success("Mídia trocada com sucesso!")
                                            st.rerun()
                    else:
                        st.info("Nenhum candidato listado. Clique no botão de re-buscar ao lado.")

                # Upload Local Custom Media
                with st.expander(f"📁 Enviar Mídia Própria para Cena {idx+1}"):
                    up_file = st.file_uploader(
                        f"Arquivo para {scene.scene_id} (MP4 ou Imagem)",
                        type=["mp4", "mov", "png", "jpg"],
                        key=f"up_{scene.scene_id}",
                    )
                    if up_file is not None:
                        if st.button(f"Aplicar Upload na {scene.scene_id}", key=f"btn_up_{scene.scene_id}"):
                            save_dir = Path("storage/media_cache")
                            saved = save_dir / f"custom_{scene.scene_id}_{up_file.name}"
                            with open(saved, "wb") as f:
                                f.write(up_file.getbuffer())
                            manager.swap_scene_media(
                                project_id=selected_project_id,
                                scene_id=scene.scene_id,
                                new_footage_path=saved,
                            )
                            st.success("Mídia própria aplicada!")
                            st.rerun()

        st.divider()
        st.markdown("### 📜 Pacote de Direitos Autorais e Créditos")
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.markdown(f"**Credits Markdown (`credits.md`):**")
            cred_path = Path(qa_data["credits_md_path"])
            if cred_path.exists():
                st.download_button(
                    "📥 Baixar credits.md",
                    data=cred_path.read_text(encoding="utf-8"),
                    file_name="credits.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
        with c_col2:
            st.markdown(f"**License Manifest (`manifest.json`):**")
            manif_path = Path(qa_data["manifest_json_path"])
            if manif_path.exists():
                st.download_button(
                    "📥 Baixar manifest.json",
                    data=manif_path.read_text(encoding="utf-8"),
                    file_name="manifest.json",
                    mime="application/json",
                    use_container_width=True,
                )

    # =========================================================================
    # TAB 3: RASCUNHO & RENDER FINAL (ETAPA 3)
    # =========================================================================
    with tab3:
        st.subheader("📱 Rascunho Vertical 9:16 & Masterização EBU R128")
        st.caption("Vídeo vertical pronto para TikTok, Reels e Shorts com -14.0 LUFS integrados e sidechain ducking de trilha sonora.")

        r_col1, r_col2 = st.columns([1, 1.2])

        with r_col1:
            if latest_video and Path(latest_video).exists():
                st.video(latest_video)
                st.caption(f"Arquivo: `{Path(latest_video).name}`")
                with open(latest_video, "rb") as f:
                    st.download_button(
                        "📥 Baixar Vídeo Masterizado (MP4)",
                        data=f,
                        file_name=f"{selected_project_id}_final.mp4",
                        mime="video/mp4",
                        type="primary",
                        use_container_width=True,
                    )
                if st.button("🚀 Aprovar Produção para Publicação", type="primary", use_container_width=True):
                    st.balloons()
                    st.success("Produção final aprovada com sucesso!")
            else:
                st.info("Vídeo draft ainda não renderizado para esta produção.")

        with r_col2:
            st.markdown("#### ⚙️ Controle de Render")
            enforce_qg = st.checkbox("Bloquear render se reprovado pelo Quality Gate", value=True)
            allow_draft = st.checkbox("Permitir render de rascunho em caso de erro menor", value=False)

            if st.button("🔨 Renderizar Vídeo Completo Agora", type="primary", use_container_width=True):
                with st.spinner("Sintetizando áudio EBU R128, gerando cards, compondo Ken Burns e renderizando vídeo..."):
                    from app.services.factory import ShortsFactory
                    factory = ShortsFactory()
                    script_file = Path(f"storage/scripts/{selected_project_id}.md")
                    script_text = script_file.read_text(encoding="utf-8") if script_file.exists() else " ".join(s.narration for s in plan.scenes)
                    res = factory.produce_draft(
                        script_id=selected_project_id,
                        script_text=script_text,
                        title=getattr(plan, "title", selected_project_id),
                        channel=getattr(plan, "channel", "default"),
                        brand_style=plan.brand_preset,
                        enforce_quality_gate=enforce_qg,
                        allow_unpassed_draft=allow_draft,
                    )
                    if res.get("video_path"):
                        st.success("Render concluído com sucesso!")
                    else:
                        st.error(f"Render bloqueado: {res.get('error', 'Erro desconhecido')}")
                    st.rerun()

            st.divider()
            st.markdown("#### 📑 Relatórios Pré-Render:")
            sb_html = Path(qa_data["storyboard_html_path"])
            if sb_html.exists():
                st.download_button(
                    "📥 Baixar Storyboard Visual (HTML)",
                    data=sb_html.read_text(encoding="utf-8"),
                    file_name="storyboard.html",
                    mime="text/html",
                    use_container_width=True,
                )
