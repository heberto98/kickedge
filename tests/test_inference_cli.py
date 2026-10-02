import json
from pathlib import Path
import subprocess
import sys

import pytest


def command(*args):
    return subprocess.run([sys.executable,'-m','kickedge','infer','--features','examples/inference_demo_2024.json',*args],capture_output=True,text=True)


def test_cli_json_and_human_output():
    if not Path('data/models/phase5/model.joblib').exists(): pytest.skip('Local frozen artifact unavailable')
    args=['--line','2.5','--side','over','--odds','+119']
    p=command(*args,'--json')
    assert p.returncode==0,p.stderr
    result=json.loads(p.stdout)
    assert result['data_quality']['demo']
    assert result['model']['feature_count']==82
    p=command(*args)
    assert p.returncode==0,p.stderr
    assert 'DEMO / TEST FIXTURE' in p.stdout
    assert 'EV' in p.stdout


@pytest.mark.parametrize('odds',['0','-99','+110junk','TOKEN_DO_NOT_ECHO','1e3'])
def test_cli_bad_input_never_echoes_value(odds):
    p=command('--line','2.5','--side','over','--odds',odds,'--json')
    assert p.returncode!=0
    assert 'error' in p.stderr.lower()
    assert 'TOKEN_DO_NOT_ECHO' not in p.stderr
    assert 'Traceback' not in p.stderr


def test_cli_quarter_line_error():
    p=command('--line','2.25','--side','over','--odds','+119')
    assert p.returncode!=0
    assert 'line' in p.stderr.lower()
