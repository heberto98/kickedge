from datetime import timedelta
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from test_current_snapshot import bundle, START


def test_cli_builds_82_features_and_runs_frozen_model(monkeypatch,capsys,tmp_path):
    assert importlib.util.find_spec('kickedge.current.cli'), 'Current CLI missing'
    if not Path('data/models/phase5/model.joblib').exists(): pytest.skip('Local model unavailable')
    from kickedge.current import cli
    from kickedge.current.engine import analyze_current_prop
    def invoke(*args,**kwargs):
        return analyze_current_prop(*args,**kwargs,clock=lambda:START+timedelta(days=42,hours=-2),
                                    source_loader=lambda *a,**k:bundle(),output_dir=tmp_path)
    monkeypatch.setattr(cli,'analyze_current_prop',invoke)
    cli.main(['--kicker','Test Kicker','--team','AAA','--opponent','BBB','--season','2027','--week','7',
              '--line','2.5','--side','over','--odds','+119','--no-market','--no-weather','--json'])
    result=json.loads(capsys.readouterr().out)
    assert result['data_quality']['feature_count']==82
    assert result['prediction']['expected_xpm']>0
    assert result['provenance']['features']['season']==2027


def test_root_analyze_help_and_invalid_input_are_safe():
    p=subprocess.run([sys.executable,'-m','kickedge','analyze','--help'],capture_output=True,text=True)
    assert p.returncode==0
    assert '--refresh-data' in p.stdout
    p=subprocess.run([sys.executable,'-m','kickedge','analyze','--kicker','Known',
                      '--team','DAL','--opponent','HOU','--line','2.5','--side','over',
                      '--odds','DO_NOT_ECHO_INPUT'],capture_output=True,text=True)
    assert p.returncode==2
    assert 'DO_NOT_ECHO_INPUT' not in p.stderr and 'Traceback' not in p.stderr
