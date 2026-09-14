import json
from click.testing import CliRunner

from rda.quality.capabilities import collect_capabilities
from rda.cli.main import cli


def test_capabilities_are_offline_and_expose_quality_contract():
    data = collect_capabilities()
    assert data["protocol"]["major"] == 1
    assert data["config_schema"] == 1
    assert data["algorithms"]
    assert "robovet" in data["delegated_checks"]
    assert "parquet" in data["dependencies"]
    assert "provider" in data
    assert "sandbox" in data


def test_capabilities_cli_json_without_training_imports():
    result = CliRunner().invoke(cli, ["capabilities", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["protocol"]["major"] == 1
    assert "training" in payload["dependencies"]

