# RDA Task Quality Profile Overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned base quality configuration plus explicit task overrides without duplicating Robovet hard checks or changing legacy `rda audit` behavior.

**Architecture:** A small pure merge function combines a full quality config with a task override that changes only metric parameters/rules and training fields. The quality CLI accepts an optional task profile, validates the merged result through `QualityConfig`, and records the resulting effective configuration hash; legacy mode remains unchanged.

**Tech Stack:** Python 3.10+, Click CLI, JSON, pytest.

## Global Constraints

- Robovet remains the authority for structural/integrity checks; RDA quality mode delegates those metrics.
- Do not change legacy `rda audit` defaults or metric implementations.
- Robot semantic profiles and trainer-window parity remain out of scope.
- Unknown override fields, metrics, or duplicate metric entries must fail before execution.
- Provisional rules may produce review advice but must not produce a final exclusion decision.

---

### Task 1: Add deterministic task-profile merge utility

**Files:**
- Create: `rda/quality/task_profiles.py`
- Test: `tests/test_quality_task_profiles.py`

**Interfaces:**
- `merge_task_profile(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]`
- Override accepts `task_id`, optional `profile_revision`, `metrics` mapping keyed by registered metric name, and optional `training` mapping. It returns a complete config mapping and never mutates inputs.

- [ ] **Step 1: Write the failing tests**

```python
def test_task_override_changes_only_metric_parameters_and_training():
    merged = merge_task_profile(BASE, {"task_id": "pusht", "metrics": {"idle_ratio": {"parameters": {"activity_epsilon": 17.8}}}})
    assert merged["quality"]["metrics"][1]["parameters"]["activity_epsilon"] == 17.8
    assert merged["quality"]["metrics"][0] == BASE["quality"]["metrics"][0]


def test_unknown_metric_and_field_are_rejected():
    with pytest.raises(ValueError, match="unknown metric"):
        merge_task_profile(BASE, {"task_id": "x", "metrics": {"missing": {}}})
    with pytest.raises(ValueError, match="unknown task profile field"):
        merge_task_profile(BASE, {"task_id": "x", "bad": 1})


def test_duplicate_base_metrics_are_rejected():
    bad = {**BASE, "quality": {"metrics": [BASE["quality"]["metrics"][0]] * 2}}
    with pytest.raises(ValueError, match="duplicate metric"):
        merge_task_profile(bad, {"task_id": "x"})
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q tests/test_quality_task_profiles.py`

Expected: collection failure because `rda.quality.task_profiles` does not exist.

- [ ] **Step 3: Implement the minimal pure merge**

Validate the base is a mapping with `quality.metrics` as a list. Index metrics by `name`, reject duplicate names, apply only `parameters` and `rule` mappings from the override, shallow-merge rule thresholds, and merge allowed training keys. Reject every other override key and reject override metrics not present in the base.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q tests/test_quality_task_profiles.py`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```bash
git add rda/quality/task_profiles.py tests/test_quality_task_profiles.py
git commit -m "feat: add task quality profile overrides"
```

### Task 2: Expose task overrides through quality CLI

**Files:**
- Modify: `rda/cli/main.py`
- Test: `tests/test_quality_task_profiles.py`

**Interfaces:**
- Add optional `--task-profile PATH` to `rda audit --mode quality`.
- `--config` remains the complete base quality config; `--task-profile` is merged before `QualityConfig.from_mapping`.

- [ ] **Step 1: Write the failing CLI test**

```python
def test_quality_cli_accepts_task_profile_option(runner, tmp_path):
    result = runner.invoke(cli, ["audit", str(dataset), "--mode", "quality", "--config", str(base), "--task-profile", str(task), "--input-manifest", str(manifest), "--run-dir", str(run_dir)])
    assert result.exit_code != 2
    assert "task profile" not in result.output.lower() or "unknown option" not in result.output.lower()
```

- [ ] **Step 2: Run the CLI test and verify it fails**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q tests/test_quality_task_profiles.py::test_quality_cli_accepts_task_profile_option`

Expected: Click rejects the unknown `--task-profile` option.

- [ ] **Step 3: Implement CLI loading and merging**

Add the option, load the optional JSON, call `merge_task_profile`, and pass the merged mapping to `QualityConfig.from_mapping`. Keep the existing requirement that quality mode needs `--config`, `--input-manifest`, and `--run-dir`. Error messages must identify invalid task-profile JSON or merge errors.

- [ ] **Step 4: Run the CLI test and quality config tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q tests/test_quality_task_profiles.py tests/test_quality_config.py`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add rda/cli/main.py tests/test_quality_task_profiles.py
git commit -m "feat: load task profile overrides in quality audit"
```

### Task 3: Add internal base and PushT profile examples

**Files:**
- Create: `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/configs/rda/base-quality.json`
- Create: `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/configs/rda/tasks/pusht.json`
- Test: `tests/test_quality_task_profiles.py`

**Interfaces:**
- Base file is a complete valid quality config with provisional rules.
- PushT file contains only `task_id`, `profile_revision`, metric overrides, and training overrides.

- [ ] **Step 1: Add JSON fixtures and a validation test**

```python
def test_checked_in_pusht_profile_merges_and_validates():
    base = json.loads(Path("configs/rda/base-quality.json").read_text())
    task = json.loads(Path("configs/rda/tasks/pusht.json").read_text())
    merged = merge_task_profile(base, task)
    config = QualityConfig.from_mapping(merged)
    assert config.effective_config_hash.startswith("sha256:")
```

- [ ] **Step 2: Run the test and verify the fixtures are absent or invalid**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q tests/test_quality_task_profiles.py::test_checked_in_pusht_profile_merges_and_validates`

Expected: FAIL because the example files do not exist yet.

- [ ] **Step 3: Add complete base and task JSON**

Keep delegated Robovet metrics out of RDA measurement rules. Mark uncalibrated task thresholds as provisional and include no robot profile until supplier semantics are available.

- [ ] **Step 4: Run validation and full quality tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q tests/test_quality_task_profiles.py tests/test_quality_config.py tests/test_quality_rules.py`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add configs/rda tests/test_quality_task_profiles.py
git commit -m "docs: add base and PushT quality profiles"
```

### Task 4: Regression verification

**Files:**
- Modify: none

- [ ] **Step 1: Run the complete RDA test suite**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. python -m pytest -q`

Expected: all existing and new tests pass.

- [ ] **Step 2: Verify legacy CLI help and metrics behavior**

Run: `python -m rda audit --help` and `python -m rda audit ./pusht --offline --metrics action_discontinuity,idle_ratio --output /tmp/rda-task-profile-regression.json`.

Expected: legacy options remain available and the command completes without consulting task profiles.

- [ ] **Step 3: Commit any test-only adjustments**

```bash
git status --short
```

Expected: only intentional implementation and fixture files are changed.
