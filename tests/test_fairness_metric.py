"""Fairness metric regression: Jain comfort must be computed on satisfaction scores.

Bug context: the learned policy left small-but-uneven comfort deficits (many homes
near zero, a few larger). Jain's index applied directly to raw deficits collapsed to
~0.37 and failed the >=0.9 gate even though every household's preferences were
essentially met and there were zero hard-constraint violations. Applied to per-home
satisfaction scores (1 = fully satisfied), the same run scores ~1.0.
"""
from fastapi.testclient import TestClient
from api.main import app
from metrics import jain, satisfaction, summarize

client = TestClient(app)

def test_satisfaction_maps_deficits_to_zero_one():
    assert satisfaction(0.0) == 1.0
    assert satisfaction(24.0) == 0.5
    assert satisfaction(48.0) == 0.0
    assert satisfaction(100.0) == 0.0  # clamped at the floor

def test_jain_on_near_zero_deficits_is_the_artifact_and_satisfaction_space_fixes_it():
    deficits = [0.0] * 40 + [0.1, 0.2, 0.3, 0.5, 0.8, 0.9, 1.0, 1.2, 1.5, 2.0]
    assert jain(deficits) < 0.9                      # old, misleading behavior
    assert jain([satisfaction(d) for d in deficits]) >= 0.99  # corrected behavior

def test_summarize_reports_household_level_detail_alongside_index():
    result = summarize(100.0, 90.0, 50.0, 20.0, [8.0, 9.0], [10.0, 10.0], [0.0, 2.0])
    assert result['comfort_deficits'] == [0.0, 2.0]
    assert result['preference_satisfaction'] == [1.0, satisfaction(2.0)]
    assert result['jain_comfort'] == jain([1.0, satisfaction(2.0)])

def test_metrics_endpoint_exposes_per_home_satisfaction():
    client.post('/simulation/reset')
    client.post('/simulation/start', json={'n_homes':50,'seed':5,'policy':'teacher'})
    client.post('/simulation/run')
    metrics = client.get('/metrics').json()
    assert len(metrics['per_home_satisfaction']) == 50
    assert all(0.0 <= v <= 1.0 for v in metrics['per_home_satisfaction'].values())
    assert metrics['worst_home_satisfaction'] == min(metrics['per_home_satisfaction'].values())
    assert metrics['jain_comfort'] >= 0.9  # teacher run keeps everyone comfortable
