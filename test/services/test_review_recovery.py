from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock
import json

import pytest

from app.services.director.schemas import Scene, ScenePlan, VisualBeat
from app.services.review.recovery import recover_pending, diagnosis


def project(tmp_path):
    media=tmp_path/'approved.mp4';media.write_bytes(b'preserved')
    approved={'asset_id':'kept','local_path':str(media),'semantic_status':'reviewed','semantic_score':1.0}
    first=Scene('one','Texto aprovado, intacto.','Objeto físico',['coffee bag'],
                visual_beats=[VisualBeat('a',duration=2,selected_media=approved),
                              VisualBeat('b',duration=3,queries=['coffee shelf'])],
                start=0,end=10,overlay={'audio_duration':10,'audio_file':'existing.wav'})
    second=Scene('two','Outra fala.','Outro objeto',['cup'],selected_media=approved,start=10,end=15)
    plan=ScenePlan('test','v1','hash',2,15,[first,second])
    path=tmp_path/'scenes.json';path.write_text(plan.to_json())
    return path,plan


def searcher(tmp_path):
    mock=Mock();mock.search_attempts=[];mock._beat_context={}
    found=tmp_path/'found.mp4';found.write_bytes(b'found')
    def populate(plan,**kwargs):
        scene=plan.scenes[0]
        scene.selected_media={'asset_id':'new','local_path':str(found),'semantic_status':'metadata_only'}
        scene.media_candidates=[deepcopy(scene.selected_media)]
    mock.populate_scene_plan.side_effect=populate
    return mock


def test_only_missing_beat_changes_and_uses_its_duration(tmp_path):
    path,original=project(tmp_path);engine=searcher(tmp_path)
    result=recover_pending(path,engine)
    actual=ScenePlan.from_dict(json.loads(path.read_text()))
    assert engine.populate_scene_plan.call_count==1
    child=engine.populate_scene_plan.call_args.args[0].scenes[0]
    assert child.end==6 # 3/5 of the measured 10 seconds, not all scene audio
    assert actual.scenes[0].narration==original.scenes[0].narration
    assert actual.scenes[0].overlay==original.scenes[0].overlay
    assert actual.scenes[0].visual_beats[0]==original.scenes[0].visual_beats[0]
    assert actual.scenes[1]==original.scenes[1]
    assert result['results'][0]['status']=='selected_for_review'
    # Found media waits for human review and is not re-searched on resume.
    engine.reset_mock()
    assert recover_pending(path,engine)['results']==[]
    engine.populate_scene_plan.assert_not_called()


def test_provider_failure_preserves_original_manifest(tmp_path):
    path,_=project(tmp_path);before=path.read_bytes();engine=searcher(tmp_path)
    engine.populate_scene_plan.side_effect=TimeoutError('provider unavailable')
    result=recover_pending(path,engine)
    assert path.read_bytes()==before
    assert result['results'][0]['status']=='search_failed'


def test_concurrent_edit_is_not_overwritten(tmp_path):
    path,_=project(tmp_path);engine=searcher(tmp_path)
    def modify(plan,**kwargs):
        path.write_text('new user edit')
    engine.populate_scene_plan.side_effect=modify
    with pytest.raises(RuntimeError,match='mudou'):
        recover_pending(path,engine)
    assert path.read_text()=='new user edit'


def test_report_masks_raw_provider_error(tmp_path):
    _,plan=project(tmp_path)
    plan.scenes[0].visual_beats[1].media_candidates=[{'error_detail':'https://example.test/?token=secret'}]
    report=diagnosis(plan)
    assert 'secret' not in json.dumps(report)
    assert report[1]['rejections']=={'outro':1}


def test_limit_and_resume_process_different_missing_plans(tmp_path):
    path,plan=project(tmp_path)
    plan.scenes[1].selected_media=None
    path.write_text(plan.to_json());engine=searcher(tmp_path)
    one=recover_pending(path,engine,limit=1)
    assert len(one['results'])==1
    two=recover_pending(path,engine,limit=1)
    assert two['results'][0]['scene']=='two'


def test_later_failure_keeps_completed_checkpoint(tmp_path):
    path,plan=project(tmp_path)
    plan.scenes[1].selected_media=None
    path.write_text(plan.to_json());engine=searcher(tmp_path)
    original=engine.populate_scene_plan.side_effect
    calls=[]
    def partial(child,**kwargs):
        calls.append(child)
        if len(calls)==2:raise TimeoutError()
        original(child,**kwargs)
    engine.populate_scene_plan.side_effect=partial
    result=recover_pending(path,engine,limit=2)
    saved=ScenePlan.from_dict(json.loads(path.read_text()))
    assert saved.scenes[0].visual_beats[1].selected_media['asset_id']=='new'
    assert saved.scenes[1].selected_media is None
    assert [r['status'] for r in result['results']]==['selected_for_review','search_failed']
