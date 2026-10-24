import json
from pathlib import Path
import subprocess

import pytest

from app.services.branding.kit import BrandKit, save_kit, load_kit
from app.services.branding.library import save_preset, list_presets
from app.services.branding.looks import VisualLook, render_look, LOOK_LABELS


@pytest.fixture
def clip(tmp_path):
    path = tmp_path/'input.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                    'testsrc2=s=160x284:r=25:d=4','-c:v','libx264','-pix_fmt','yuv420p',str(path)], check=True)
    return path


def frame(path):
    return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])


@pytest.mark.parametrize('preset', list(LOOK_LABELS)[1:])
def test_real_filters_preserve_timing_and_change_pixels(clip, preset, tmp_path):
    original = clip.read_bytes()
    look = VisualLook(preset=preset, intensity=0.8, grain=0.3, vignette=0.3)
    result = render_look(clip, look, tmp_path/'cache', source_in=1, duration=2)
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(result)]))
    assert abs(float(probe['format']['duration']) - 2) < 0.1
    assert (probe['streams'][0]['width'],probe['streams'][0]['height']) == (160,284)
    assert frame(result) != frame(clip)
    assert clip.read_bytes() == original
    assert render_look(clip, look, tmp_path/'cache', source_in=1, duration=2) == result
    assert render_look(clip, look.model_copy(update={'intensity':0.2}), tmp_path/'cache', source_in=1, duration=2) != result


def test_identity_and_zero_intensity_bypass(clip, tmp_path):
    for preset in LOOK_LABELS:
        look = VisualLook(preset=preset, intensity=0)
        assert look.filters() == ''
        assert render_look(clip,look,tmp_path/'cache',duration=2) == clip


def test_short_interval_does_not_leave_cached_output(clip,tmp_path):
    with pytest.raises(ValueError,match='fim do vídeo'):
        render_look(clip,VisualLook(preset='warm'),tmp_path/'cache',source_in=3,duration=3)
    assert not list((tmp_path/'cache').glob('*.mp4'))


def test_presets_and_project_snapshot_are_independent(tmp_path):
    root=tmp_path/'presets'
    a=BrandKit(channel='Canal A',name='Documental',look=VisualLook(preset='documentary'))
    b=BrandKit(channel='Canal B',name='Quente',look=VisualLook(preset='warm'))
    aid=save_preset(a,root=root);bid=save_preset(b,root=root)
    save_kit(a,tmp_path/'project.json')
    a.look.preset='archive'
    save_preset(a,aid,root=root)
    assert list_presets(root)[bid] == b
    assert load_kit(tmp_path/'project.json').look.preset == 'documentary'
    assert save_preset(a,root=root) not in {aid,bid}
    with pytest.raises(ValueError):save_preset(a,'../bad',root)


def test_old_kit_keeps_identity_look():
    assert BrandKit.model_validate({'name':'Antigo','version':1}).look.filters() == ''
    with pytest.raises(ValueError):VisualLook(preset='arbitrary filter')
    with pytest.raises(ValueError):VisualLook(intensity=float('nan'))


def test_preview_keeps_same_interval_and_is_bounded(clip,tmp_path):
    result=render_look(clip,VisualLook(preset='warm'),tmp_path/'preview',source_in=1,duration=2,preview=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(result)]))
    assert abs(float(probe['format']['duration'])-2)<0.1
    assert probe['streams'][0]['width']<=540 and probe['streams'][0]['height']<=960
