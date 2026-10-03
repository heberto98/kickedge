from datetime import timedelta
import importlib
import json
from pathlib import Path

import pytest

from test_current_snapshot import START, bundle


def api():
    assert importlib.util.find_spec('kickedge.current.engine'), 'Current orchestrator missing'
    return importlib.import_module('kickedge.current.engine')


def test_manual_end_to_end_without_optional_providers(tmp_path):
    if not Path('data/models/phase5/model.joblib').exists(): pytest.skip('Local model unavailable')
    now=START+timedelta(days=42,hours=-2)
    def broken_context(*a,**k):
        return {'context':{'market':{'available':False},'weather':{'available':False}},
                'prop_quotes':[],'provider_timestamps':{},'warnings':['Parlay unavailable'],
                'source_failures':[{'provider':'parlay','critical':False,'reason':'timeout'}]}
    result=api().analyze_current_prop('Test Kicker','AAA','BBB',2.5,'over',119,
        season=2027,week=7,root=Path('.'),clock=lambda:now,
        source_loader=lambda *a,**k:bundle(),context_collector=broken_context,
        output_dir=tmp_path)
    assert result['data_quality']['feature_count']==82
    assert result['data_quality']['model_verified']
    assert result['data_quality']['prop_availability']=='manual'
    assert result['prediction']['expected_xpm']>0
    assert result['context']['market']['available'] is False
    assert result['provenance']['features']['latest_game_used']['game_id']=='2027_06_AAA_BBB'
    json.dumps(result,allow_nan=False)
    assert len(list(tmp_path.glob('*/snapshot.json')))==1


def test_invalid_manual_quote_fails_before_source_download():
    def forbidden(*a,**k): pytest.fail('Invalid quote should fail before source download')
    with pytest.raises(ValueError,match='line'):
        api().analyze_current_prop('Test Kicker','AAA','BBB',2.25,'over',119,source_loader=forbidden)


def test_optional_quote_ambiguity_requires_manual_input():
    m=api()
    quote={'line':2.5,'over_price':119,'under_price':-140,'bookmaker':'fliff',
           'source':'provider','observed_at':START.isoformat()}
    with pytest.raises(ValueError,match='ambiguous'):
        m.select_quote([quote,quote|{'bookmaker':'fanduel'}],2.5,'over',None,None,None)
    with pytest.raises(ValueError,match='manual'):
        m.select_quote([],2.5,'over',None,None,None)
    selected=m.select_quote([quote],2.5,'over',None,None,None)
    assert selected['odds']==119 and selected['source']=='fliff'
