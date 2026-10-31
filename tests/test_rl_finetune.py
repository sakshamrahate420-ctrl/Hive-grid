"""Regression tests for the RL fine-tuning reward and training loop shapes."""
import subprocess
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl_finetune import DEVICE_SCALES, reward  # noqa: E402


def _observations(batch: int = 8, steps: int = 48) -> torch.Tensor:
    obs = torch.rand(batch, steps, 18)
    obs[..., 4] = torch.rand(batch, steps)          # price feature in [0, 1]
    obs[..., 5] = (torch.rand(batch, steps) > 0.5).float()  # stress flag
    return obs


def test_reward_accepts_sequence_actions_and_broadcasts_per_step_actions():
    """The original bug: [batch, 7] actions crashed against [batch, 48, FEATURES] observations."""
    obs = _observations()
    per_step = reward(torch.rand(8, 48, 7), obs)
    assert per_step.shape == (8, 48, 1)
    broadcast = reward(torch.rand(8, 7), obs)       # policy head emits one action vector per sequence
    assert broadcast.shape == (8, 48, 1)


def test_reward_prefers_less_import_during_stress():
    obs = _observations(batch=4)
    low = torch.zeros(4, 7)
    high = torch.ones(4, 7)
    r_low = reward(low, obs).mean()
    r_high = reward(high, obs).mean()
    assert r_low > r_high                            # more load is penalized
    assert torch.isfinite(r_low) and torch.isfinite(r_high)


def test_reward_penalizes_out_of_range_actions():
    obs = _observations(batch=4)
    in_range = reward(torch.full((4, 7), 0.5), obs).mean()
    out_of_range = reward(torch.full((4, 7), 2.0), obs).mean()
    assert out_of_range < in_range                  # violation term kicks in


def test_reward_scales_match_collect_normalization():
    assert DEVICE_SCALES == (6.0, 8.0, 1.2, 1.0, 3.0, 3.0, 10.0)
    obs = torch.zeros(1, 48, 18)
    full = reward(torch.ones(1, 7), obs)            # all devices at nominal max, no solar/base load
    # ac 6 + ev 8 + geyser 1.2 + other 1 + charge 3 - discharge 3 = 16.2 kW import
    expected_peak_term = 0.25 * (16.2 * 0.5) ** 2
    assert torch.allclose(full[..., 0], torch.full_like(full[..., 0], -(expected_peak_term + 0.35 * 100.0)), atol=1e-3)


def test_smoke_training_loop_runs(tmp_path):
    output = tmp_path / "hive_policy_rl.pt"
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "rl_finetune.py"),
         "--smoke", "--model", str(tmp_path / "missing.pt"), "--output", str(output)],
        capture_output=True, text=True, timeout=300,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr
    assert output.exists()
    saved = torch.load(output, map_location="cpu", weights_only=True)
    assert saved["fine_tuned"] == "home_reward_policy"
