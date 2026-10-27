from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
import pytest

from app.services.review.search_assistant import suggest_queries
from app.services.review.benchmark import load_cases, record_rating, summarize, search_case
from app.services.review.curation import curate_asset
from app.services.media_ranker.smart_library import SmartLibrary


def test_suggestions_keep_action_and_require_explicit_application():
    queries=['cashier scanning coffee bag checkout']
    original=list(queries)
    suggestions=suggest_queries(queries)
    assert suggestions[0]['query']=='cashier scanning coffee package checkout'
    assert queries==original
    assert 'Confira' in suggestions[0]['reason']


def test_suggestions_respect_exclusions_abstract_terms_and_deduplication():
    assert suggest_queries(['coffee bag shelf'],['package'])==[]
    assert suggest_queries(['coffee bag market'])==[]
    assert len(suggest_queries(['coffee bag shelf','coffee bag shelf']))==1
    assert suggest_queries(['unknown subject action'])==[]


def test_benchmark_has_30_distinct_concrete_briefs_and_no_default_ratings(tmp_path):
    cases=load_cases()
    assert len(cases)==30 and len({c['id'] for c in cases})==30
    assert all(len(c['queries'])==3 for c in cases)
    assert summarize(tmp_path)['ratings']==0
    assert summarize(tmp_path)['reviewed_cases']==0


def test_search_does_not_create_human_ratings(tmp_path):
    searcher=Mock(); searcher.search_for_scene.return_value=[];searcher.search_attempts=[]
    result=search_case('case_01',searcher)
    assert result['candidates']==[]
    assert summarize(tmp_path)['ratings']==0
    assert searcher.search_for_scene.call_args.kwargs['target_duration']==4


def test_benchmark_revisions_do_not_inflate_counts(tmp_path):
    clip=tmp_path/'clip.mp4';clip.write_bytes(b'fixture')
    candidate={'asset_id':'a','local_path':str(clip)}
    root=tmp_path/'ratings'
    record_rating('case_01',candidate,reviewer='Reviewer',subject=True,action=False,framing=True,root=root)
    record_rating('case_01',candidate,reviewer='Reviewer',subject=True,action=True,framing=True,root=root)
    report=summarize(root)
    assert report['ratings']==1 and report['accepted_ratings']==1 and report['reviewed_cases']==1
    with pytest.raises(ValueError):record_rating('case_01',candidate,reviewer='',subject=True,action=True,framing=True,root=root)
    with pytest.raises(ValueError):record_rating('case_01',candidate,reviewer='R',subject=None,action=True,framing=True,root=root)


def test_curated_asset_keeps_provenance_and_is_not_approved_in_new_context(tmp_path):
    path=tmp_path/'image.png';Image.new('RGB',(720,1280),'red').save(path)
    candidate={'asset_id':'../asset','local_path':str(path),'semantic_status':'reviewed',
               'rights_status':'allowed','creator_name':'Creator','license_id':'CC0',
               'perceptual_hash':'abc','description':'original metadata'}
    before=deepcopy(candidate)
    asset=curate_asset(candidate,'Coffee bag on shelf',['coffee bag','shelf'],tmp_path/'library')
    assert Path(asset.local_path).parent==tmp_path/'library'
    found=SmartLibrary(tmp_path/'library').search_library('coffee bag shelf')
    assert len(found)==1 and found[0].creator_name=='Creator'
    assert found[0].perceptual_hash=='abc' and found[0].license_id=='CC0'
    assert found[0].semantic_status=='unverified'
    assert candidate==before
    assert not (tmp_path/'asset.png').exists()


@pytest.mark.parametrize('change',[{'semantic_status':'unverified'},{'rights_status':'rights_unknown'}, {'rights_status':''}, {'rights_status':'blocked_for_this_use'}, {'is_synthetic':True}])
def test_unreviewed_or_restricted_assets_do_not_enter_library(tmp_path,change):
    path=tmp_path/'image.png';Image.new('RGB',(20,20)).save(path)
    candidate={'asset_id':'a','local_path':str(path),'semantic_status':'reviewed','rights_status':'allowed',**change}
    with pytest.raises(ValueError):curate_asset(candidate,'Description',['object'],tmp_path/'library')
    assert not (tmp_path/'library/catalog.json').exists()
