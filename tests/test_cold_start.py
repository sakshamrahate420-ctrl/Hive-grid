from api.main import SimulationManager, StartRequest
from pytest import approx


def test_warm_start_uses_setpoints_and_per_home_ev_trip_energy():
    manager = SimulationManager()
    manager.start(StartRequest(
        n_homes=56,
        seed=7,
        policy='teacher',
        scenario='heatwave',
        demo_date='2023-05-14',
        weather_year=2023,
    ))

    ev_start_percentages = set()
    for home in manager.homes:
        state = manager.home_stats[home.id]
        assert state['room_temp'] == home.temperature_setpoint_c
        if home.battery_kwh:
            assert state['soc'] == home.battery_kwh * 0.5
        if home.ev_kw:
            assert state['ev_initial_soc'] == approx(home.initial_ev_soc_kwh)
            assert state['ev_remaining'] == approx(home.ev_energy_need_kwh)
            assert state['baseline_ev_remaining'] == approx(home.ev_energy_need_kwh)
            ev_start_percentages.add(state['ev_initial_soc'] / home.ev_battery_kwh)

    assert len(ev_start_percentages) > 1
