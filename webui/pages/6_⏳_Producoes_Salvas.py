"""Persistent production status and partial delivery."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

st.set_page_config(page_title='Produções salvas', page_icon='⏳', layout='wide')
st.title('⏳ Produções salvas')
st.caption('Retomada automática 24 horas após atingir a cota. O computador deve estar ligado, com sua sessão ativa e internet. Se estiver desligado, a tentativa ocorre quando o serviço voltar.')
if st.button('Atualizar situação'):
    st.rerun()
labels = {'waiting_quota': 'Aguardando renovação da cota', 'running': 'Em processamento / retomada pendente',
          'completed': 'Concluída', 'needs_review': 'Precisa de revisão editorial', 'failed': 'Falhou', 'cancelled': 'Retomada cancelada'}
for path in sorted(Path('storage/projects').glob('*/production_job.json'), reverse=True):
    job = json.loads(path.read_text())
    with st.expander(f"{job['params'].get('title') or path.parent.name} — {labels.get(job['status'], job['status'])}", expanded=True):
        st.caption(path.parent.name)
        st.write(f"Cenas com áudio salvo: {len(list((path.parent/'audio').glob('*.receipt.json')))}")
        if job['status'] == 'waiting_quota':
            when = datetime.fromtimestamp(job['next_attempt_at'], ZoneInfo('America/Sao_Paulo'))
            st.info(f"Próxima tentativa: {when:%d/%m/%Y às %H:%M} (Brasília)")
            if st.button('Cancelar retomada automática', key=path.parent.name):
                from app.services.production.resume import project_lock, write_json
                try:
                    with project_lock(path.parent):
                        current = json.loads(path.read_text())
                        current['status'] = 'cancelled'
                        write_json(path, current)
                    st.rerun()
                except RuntimeError as exc:
                    st.warning(str(exc))
        result = job.get('result', {})
        if result.get('video_path') and Path(result['video_path']).is_file():
            st.video(result['video_path'])
        if job['status'] == 'needs_review':
            st.page_link('pages/1_🎬_Scene_Review.py', label='Abrir revisão editorial')
        partial = path.parent/'entrega_parcial'
        if (partial/'narracao_parcial.mp3').exists():
            st.audio(str(partial/'narracao_parcial.mp3'))
        if (partial/'entrega_parcial.zip').exists():
            st.download_button('Baixar áudios e roteiro', (partial/'entrega_parcial.zip').read_bytes(),
                               file_name=f'{path.parent.name}_parcial.zip', key=f'zip_{path.parent.name}')
        if job.get('error'):
            st.caption(job['error'])
