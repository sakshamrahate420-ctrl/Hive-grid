from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_step_run_and_restart_reset_resume_the_same_day():
    client.post('/simulation/reset')
    request = {
        'n_homes': 50,
        'seed': 19,
        'policy': 'teacher',
        'scenario': 'summer',
        'demo_date': '2023-05-14',
        'weather_year': 2023,
    }
    started = client.post('/simulation/start', json=request)
    assert started.status_code == 200
    assert started.json()['current_step'] == 0
    original_homes = client.get('/homes').json()
    assert client.get('/data/provenance').json()['demo_date'] == '2023-05-14'

    stepped = client.post('/simulation/step', json={'n_steps': 4})
    assert stepped.status_code == 200
    assert stepped.json()['current_step'] == 4
    assert len(client.get('/timeseries').json()['steps']) == 4

    reset = client.post('/simulation/reset?restart=true')
    assert reset.status_code == 200
    assert reset.json()['current_step'] == 0
    assert client.get('/data/provenance').json()['demo_date'] == '2023-05-14'
    assert [home['profile'] for home in client.get('/homes').json()] == [home['profile'] for home in original_homes]
    assert client.get('/timeseries').json()['steps'] == []

    completed = client.post('/simulation/run')
    assert completed.status_code == 200
    assert completed.json()['state']['current_step'] == 96
    assert len(client.get('/timeseries').json()['steps']) == 96
