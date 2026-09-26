import pytest

from kickedge.labels import reconcile


@pytest.mark.parametrize('xpa,xpm', [(0,0),(4,4),(3,2),(1,0)])
def test_agreement_including_explicit_zero(xpa,xpm):
    assert reconcile(xpa,xpm,xpa,xpm,True,True) == (xpa,xpm,'agreed')


@pytest.mark.parametrize('values,status', [
    ((None,None,0,0,True,True),'missing_player_stats'),
    ((0,0,None,None,True,True),'missing_pbp'),
    ((0,0,0,0,True,False),'participation_unverified'),
    ((0,0,0,0,False,True),'incomplete_pbp'),
    ((3,2,3,3,True,True),'source_discrepancy'),
    ((-1,0,0,0,True,True),'invalid_count'),
    ((1,2,1,2,True,True),'invalid_count'),
    ((1.5,1,1.5,1,True,True),'invalid_count'),
    ((1,0,1,0,True,True,1),'unknown_pat_result'),
])
def test_unknown_and_inconsistent_values_never_publish(values,status):
    assert reconcile(*values) == (None,None,status)
