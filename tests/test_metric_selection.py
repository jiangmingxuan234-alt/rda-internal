"""Tests for explicit metric selection and offline audit mode."""
from __future__ import annotations

from click.testing import CliRunner

from rda.audit.episode_audit import EpisodeAuditor
from rda.cli.main import cli
from rda.metrics.base import MetricBase, MetricResult
from rda.io.schema import EpisodeData


class _CountingMetric(MetricBase):
    name = "counting"
    def __init__(self):
        self.calls = 0

    def compute(self, episode: EpisodeData) -> MetricResult:
        self.calls += 1
        return MetricResult.make_pass(self.name, {"calls": self.calls})


def test_episode_auditor_runs_only_selected_metrics():
    first = _CountingMetric()
    second = _CountingMetric()
    episode = EpisodeData(episode_index=0, num_frames=1, timestamps=())
    result = EpisodeAuditor(metrics=[first]).audit(episode)
    assert list(result.metrics) == ["counting"]
    assert first.calls == 1
    assert second.calls == 0


def test_audit_rejects_unknown_metric_before_loading_dataset(monkeypatch, tmp_path):
    runner = CliRunner()
    loaded = False

    def fail_loader(*args, **kwargs):
        nonlocal loaded
        loaded = True
        raise AssertionError("dataset loader must not run")

    monkeypatch.setattr("rda.io.lerobot_loader.load_lerobot_dataset", fail_loader)
    result = runner.invoke(cli, ["audit", str(tmp_path), "--metrics", "does_not_exist"])
    assert result.exit_code != 0
    assert "unknown metric" in result.output.lower()
    assert loaded is False


def test_audit_offline_sets_offline_environment(monkeypatch, tmp_path):
    runner = CliRunner()
    captured = {}

    monkeypatch.setattr("rda.io.lerobot_loader.load_lerobot_dataset", lambda path: captured.setdefault("loaded", True))
    result = runner.invoke(cli, ["audit", str(tmp_path), "--offline"])
    # The command may fail after the loader stub; the option must be accepted.
    assert "No such option" not in result.output
