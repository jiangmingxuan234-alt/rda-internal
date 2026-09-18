"""Bounded, resumable quality-mode execution."""
from dataclasses import dataclass
from pathlib import Path
import json, hashlib, os, shutil
from .checkpoint import CheckpointStore
from .resources import ResourceBudget, BudgetGuard, BudgetExceeded
from .contracts import QualityRunState

@dataclass(frozen=True)
class QualityRunSummary:
    run_id: str; run_state: QualityRunState; planned: int; completed: int; skipped: int; failed: int; output_root: Path; reason_codes: tuple[str,...]=()
    def to_dict(self): return {'run_id':self.run_id,'run_state':self.run_state.value,'planned':self.planned,'completed':self.completed,'skipped':self.skipped,'failed':self.failed,'reason_codes':list(self.reason_codes)}


def _publish_execution_artifacts(staging: Path, final_bundle: Path) -> None:
    """Copy the authoritative plan/results into the published bundle.

    The report writer publishes advice and its report, while the runner owns
    the execution plan and terminal result stream.  A complete marker must
    never point at a directory that lacks either of those reconciliation
    inputs, so both files are copied and included in the existing checksum
    index before the caller writes the marker.
    """
    checksums_path = final_bundle / "checksums.json"
    try:
        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("published quality bundle has no valid checksums.json") from exc
    if not isinstance(checksums, dict):
        raise ValueError("published quality bundle checksums must be an object")
    for name in ("execution_plan.json", "unit_results.jsonl"):
        source = staging / name
        if not source.is_file():
            raise FileNotFoundError(f"missing execution artifact: {source}")
        destination = final_bundle / name
        shutil.copyfile(source, destination)
        checksums[name] = "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()
    checksums_path.write_text(
        json.dumps(checksums, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

def _build_manifest_plan(request, manifest, config):
    """Create a stable non-empty plan from the verified manifest and config."""
    from .execution_plan import build_plan

    metrics = list(config.quality.get("metrics", ()))
    if not metrics:
        raise ValueError("quality.metrics must contain at least one metric")
    if config.robot is not None:
        groups = list(config.robot.get("dimension_groups", {}).keys()) or ["default"]
        cameras = list(config.robot.get("cameras", ())) or ["default"]
    else:
        groups, cameras = ["default"], ["default"]
    specs = []
    for episode_id in manifest.expected_episode_ids:
        episode = manifest.episodes[episode_id]
        for metric in metrics:
            name = metric["name"]
            selected = cameras if name in {"visual_quality", "video_freeze", "video_stream_sync", "video_timestamp_alignment"} else groups
            for group in selected:
                sampling_range = {"planned_samples": episode.declared_length}
                if name in {"visual_quality", "video_freeze", "video_stream_sync", "video_timestamp_alignment"}:
                    sampling_range.update({"from_timestamp": episode.timestamp_from, "to_timestamp": episode.timestamp_to})
                specs.append({
                    "episode_id": str(episode_id),
                    "metric": name,
                    "camera_or_dimension_group": group,
                    "input_references": {
                        "manifest_episode_id": episode_id,
                        "robot_profile": manifest.robot_profile,
                    },
                    "requested_config_hash": config.requested_config_hash,
                    "effective_config_hash": config.effective_config_hash,
                    "sampling_range": sampling_range,
                    "resource_estimate": {"frames": episode.declared_length},
                })
    return build_plan(specs)


def _real_executor(manifest, config):
    from rda.io.lerobot_loader import iter_episodes
    from .measurements import measure_unit
    from .rules import evaluate_measurement

    episodes = {str(episode.episode_index): episode for episode in iter_episodes(str(manifest.dataset_root))}
    metric_rules = {item["name"]: item.get("rule") for item in config.quality.get("metrics", ())}

    def execute(unit):
        episode = episodes.get(str(unit.episode_id))
        if episode is None:
            raise ValueError(f"episode {unit.episode_id} is absent from dataset")
        record = measure_unit(unit, episode, None, config)
        return evaluate_measurement(record, metric_rules.get(unit.metric))

    return execute


def _write_real_artifacts(staging: Path, run_id: str, plan, results, *, run_state: str):
    from .report import write_quality_bundle

    plan_path = staging / "execution_plan.json"
    plan_path.write_text(json.dumps({"schema_version": 1, "run_id": run_id,
                                     "units": [unit.to_dict() for unit in plan.units]},
                                    sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result_rows = [result.to_dict() for result in results]
    (staging / "unit_results.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in result_rows), encoding="utf-8")
    paths = write_quality_bundle(staging, run_id, results, run_state=run_state,
                                 metadata={"execution_plan": "execution_plan.json"})
    final_bundle = staging.parent / run_id
    if final_bundle.exists():
        shutil.rmtree(final_bundle)
    os.replace(paths["bundle"], final_bundle)
    _publish_execution_artifacts(staging, final_bundle)
    marker = staging.parent / f"{run_id}.complete"
    marker.write_text("complete\n", encoding="utf-8")
    return final_bundle


def run_quality(request, *, plan=None, execute_unit=None, budget=None):
    budget = budget or ResourceBudget(); guard=BudgetGuard(budget)
    out=Path(request.output_root); staging=out/(request.run_id+'.staging'); staging.mkdir(parents=True,exist_ok=True)
    store=CheckpointStore(staging, request.run_id); cached=store.load(request.run_id)
    real_mode = plan is None and hasattr(request, "input_manifest") and hasattr(request, "dataset_root") and "quality" in request.config
    manifest = config = plan_obj = None
    if real_mode:
        from .config import QualityConfig
        from .input_manifest import load_quality_manifest, verify_producer_artifact
        from .execution_plan import build_plan
        manifest = load_quality_manifest(Path(request.input_manifest))
        verify_producer_artifact(manifest)
        config = QualityConfig.from_mapping(request.config)
        plan_obj = _build_manifest_plan(request, manifest, config)
        units = list(plan_obj.units)
        execute_unit = execute_unit or _real_executor(manifest, config)
    else:
        units=list(plan or request.config.get('execution_plan', []))
    results=[]; reasons=[]; failed=skipped=0
    plan_hash='sha256:'+hashlib.sha256(json.dumps(units,sort_keys=True,default=str).encode()).hexdigest()
    config_hash='sha256:'+hashlib.sha256(json.dumps(request.config,sort_keys=True,default=str).encode()).hexdigest()
    prior=store.state()
    if request.resume and prior and (prior.get('plan_hash') != plan_hash or prior.get('config_hash') != config_hash):
        cached={}; reasons.append('RESUME_BINDING_MISMATCH')
    stopped=False
    for index, unit in enumerate(units):
        pid=unit.get('plan_unit_id') if isinstance(unit,dict) else getattr(unit,'plan_unit_id')
        if request.resume and pid in cached: results.append(cached[pid]); continue
        try:
            guard.check(); result=execute_unit(unit) if execute_unit else (unit if isinstance(unit,dict) else unit.to_dict())
            store.save_unit(result); results.append(result)
        except BudgetExceeded as exc:
            reasons.append(exc.reason); stopped=True
            for rest in units[index:]:
                rid = rest.get('plan_unit_id') if isinstance(rest,dict) else getattr(rest,'plan_unit_id')
                row={'plan_unit_id':rid,'execution_state':'SKIPPED','reason_codes':[exc.reason]}; store.save_unit(row); results.append(row); skipped += 1
            break
        except Exception as exc:
            failed += 1; reasons.append('UNIT_FAILED'); row={'plan_unit_id':pid,'execution_state':'FAILED','reason_codes':['UNIT_FAILED']}; store.save_unit(row); results.append(row)
    if skipped or failed: state=QualityRunState.PARTIAL
    else: state=QualityRunState.COMPLETED
    store.mark_stage('publish', run_state=state.value, planned=len(units), completed=len(results), plan_hash=plan_hash, config_hash=config_hash)
    marker=out/(request.run_id+'.complete')
    if real_mode:
        typed_results = [result for result in results if hasattr(result, "to_dict")]
        if state is QualityRunState.COMPLETED and len(typed_results) == len(units):
            _write_real_artifacts(staging, request.run_id, plan_obj, typed_results, run_state=state.value)
        elif marker.exists():
            marker.unlink()
    elif state is QualityRunState.COMPLETED:
        marker.write_text('complete\n')
    return QualityRunSummary(request.run_id,state,len(units),len(results)-skipped,skipped,failed,out,tuple(reasons))
