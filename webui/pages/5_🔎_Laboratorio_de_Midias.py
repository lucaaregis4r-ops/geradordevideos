"""Explicit human benchmark, separate from production scripts and approval."""
from pathlib import Path
import streamlit as st
from app.services.review.benchmark import load_cases, search_case, record_rating, summarize

st.set_page_config(page_title='Laboratório de mídias', page_icon='🔎', layout='wide')
st.title('🔎 Laboratório de pesquisa de mídias')
st.caption('30 cenas para avaliar objetos, ações e enquadramento. As notas são humanas; buscar ou avaliar aqui não altera produções.')
if st.session_state.pop('benchmark_saved', False):
    st.success('Avaliação registrada. Ela não aprova nem substitui mídia em uma produção.')
summary=summarize()
a,b=st.columns(2)
a.metric('Casos com avaliação humana',f"{summary['reviewed_cases']} / {summary['total_cases']}")
b.metric('Avaliações que passaram nos três critérios',f"{summary['accepted_ratings']} / {summary['ratings']}")
if summary['results']:
    import json
    st.download_button('Exportar avaliações',json.dumps(summary,ensure_ascii=False,indent=2),'benchmark.json','application/json')
cases={c['id']:c for c in load_cases()}
case_id=st.selectbox('Cena de avaliação',list(cases),format_func=lambda x:f"{x} · {cases[x]['brief']}")
case=cases[case_id]
st.write(case['brief'])
st.code('\n'.join(case['queries']),language=None)
if st.button('Pesquisar candidatos deste caso'):
    from app.services.media_ranker.media_searcher import MediaSearcher
    try:
        with st.spinner('Consultando fontes…'):
            st.session_state[f'benchmark_{case_id}']=search_case(case_id,MediaSearcher())
    except Exception as exc:
        st.error(f'Pesquisa falhou ({type(exc).__name__}). Nenhuma avaliação foi criada.')
result=st.session_state.get(f'benchmark_{case_id}')
if result:
    if not result['candidates']:
        st.info('Nenhum candidato retornado. Isso não é uma avaliação humana de relevância.')
    else:
        i=st.selectbox('Candidato para avaliar',range(len(result['candidates'])),format_func=lambda i:f"{i+1} · {result['candidates'][i].get('provider')} · {result['candidates'][i].get('description') or result['candidates'][i]['asset_id']}",key=f'choice_{case_id}')
        candidate=result['candidates'][i]
        local=candidate.get('local_path')
        if local and Path(local).is_file():
            if Path(local).suffix.lower() in {'.jpg','.jpeg','.png','.webp'}:st.image(local)
            else:st.video(local)
            with st.form(f'rating_{case_id}_{i}'):
                reviewer=st.text_input('Nome do avaliador')
                subject=st.radio('O objeto principal corresponde?', ['Não avaliado','Sim','Não'])
                action=st.radio('A ação solicitada aparece?', ['Não avaliado','Sim','Não'])
                framing=st.radio('O enquadramento permite reconhecer objeto e ação?', ['Não avaliado','Sim','Não'])
                notes=st.text_area('Observações')
                if st.form_submit_button('Registrar avaliação humana'):
                    if 'Não avaliado' in (subject,action,framing):st.error('Avalie os três critérios.')
                    else:
                        try:
                            record_rating(case_id,candidate,reviewer=reviewer,subject=subject=='Sim',action=action=='Sim',framing=framing=='Sim',notes=notes)
                            st.session_state['benchmark_saved']=True
                            st.rerun()
                        except ValueError as exc:st.error(str(exc))
        elif st.button('Carregar mídia para assistir'):
            from app.services.media_ranker.media_searcher import MediaSearcher
            from app.services.media_ranker.schemas import MediaCandidate
            try:
                downloaded=MediaSearcher()._download_candidate_asset(MediaCandidate.from_dict(candidate))
                if downloaded and Path(downloaded).is_file():
                    candidate['local_path']=downloaded
                    st.rerun()
                st.error('Arquivo indisponível.')
            except Exception as exc:st.error(f'Falha ao carregar ({type(exc).__name__}).')
