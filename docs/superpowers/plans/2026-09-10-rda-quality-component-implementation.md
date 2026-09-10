# RDA Training Quality Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 RDA 中实现可追溯、可恢复、与真实训练 loader 对齐的 LeRobot v3 训练质量分析模式，并通过 Adapter 输出给公司核心和 FiftyOne 使用；RDA 不生成采购最终结论或正式训练清单。

**Architecture:** RDA 新增独立 `quality` 请求/响应路径，复用现有 LeRobot loader、指标和统计实现，但用版本化 measurement、metric-local rule、执行计划和四层状态替代旧的单一 `MetricResult` 结论。Adapter 负责 Robovet full 验收门禁、身份/episode 对账和兼容投影；公司核心保存审核事件并分别生成采购质量结论与训练选择结论，FiftyOne 只展示证据和采集人工决定。

**Tech Stack:** Python 3.10+；Click CLI；NumPy；pandas/pyarrow；PyAV（视觉可选依赖）；JSON/JSONL；pytest；现有 RDA `MetricBase`、LeRobot v3 loader、ReferenceProfile；Robovet Adapter 的结构化报告契约。

## Global Constraints

- 只读输入：LeRobot 数据快照和 Robovet 证据目录禁止被 RDA/Adapter 写入；输出、缓存、恢复状态位于数据目录之外。
- 默认离线：质量模式不调用 `recommend` 远程服务，不下载模型权重；缺依赖按计划单元报告，不静默跳过。
- 组件边界：Robovet 负责基础验收和机器人语义/硬范围；RDA 负责训练质量 measurement 与规则建议；Adapter 不维护第二套评分；FiftyOne 不保存公司的唯一权威决定。
- 决策边界：`quality_advice.jsonl` 是 RDA 候选建议；正式 `procurement_quality_decision`、`training_selection_decision` 和训练清单只能由公司核心生成。
- 状态边界：新链路必须记录 `applicability`、`execution_state`、`assessment`、`run_state`；Adapter 原六态只能作为兼容字段派生。
- 执行计划：每个 `episode × metric × camera_or_dimension_group` 产生一个稳定 `plan_unit_id`，每个计划单元发布恰好一个终态结果。
- 质量规则：测量成功且没有规则只能是 `COMPUTED + UNASSESSED`；不得使用旧 `MetricResult.make_pass`、默认参数重算或缺失值填零。
- 训练窗口：优先消费固定版本真实训练 loader 的候选窗口索引；不支持的 delta timestamp、padding、horizon、对齐或多相机容差语义输出 `UNASSESSED`。
- 版本与 hash：requested/effective 配置、算法、规则、依赖和输入身份使用规范化 JSON hash，并在报告中回显。
- 兼容性：现有 legacy `rda audit` 和旧 Adapter 产物保持显式 legacy 路径；新质量模式报告使用独立主版本，禁止按字段猜测跨版本。
- 测试纪律：每项实现先写失败测试，再实现最小行为；合成数据只能证明接口和缺陷注入，不代表真实采购数据校准完成。

---

## Task 1: 建立 quality 请求、配置和四层结果契约

**Files:**
- Create: `rda/quality/__init__.py`
- Create: `rda/quality/contracts.py`
- Create: `rda/quality/config.py`
- Create: `rda/quality/execution_plan.py`
- Modify: `rda/metrics/base.py`（只保留 legacy API，不改变旧调用方）
- Test: `tests/test_quality_contracts.py`
- Test: `tests/test_quality_config.py`
- Test: `tests/test_quality_execution_plan.py`

**Interfaces:**
- `QualityRequest(dataset_root: Path, input_manifest: Path, config: Mapping, output_root: Path, run_id: str, resume: bool = False)`：质量模式输入。
- `QualityConfig.from_mapping(value) -> QualityConfig`：解析并校验 robot/quality/training 三类配置，拒绝未知字段和互相矛盾字段。
- `PlanUnit`：包含 `plan_unit_id`、episode ID、metric、camera_or_dimension_group、输入引用、requested/effective config hash、采样范围和资源估计。
- `UnitResult`：包含 `plan_unit_id`、`applicability`、`execution_state`、`assessment`、`coverage`、`measurement`、`evidence`、`reason_codes`。
- `QualityRunState`：`COMPLETED / PARTIAL / BLOCKED / ERROR / INTERRUPTED`。

- [ ] **Step 1: 写状态与契约失败测试。** 在 `tests/test_quality_contracts.py` 覆盖四层枚举、非法字符串、`EXCLUDE_CANDIDATE` 不被转换为正式业务排除、缺少 `plan_unit_id`、measurement 与 UNASSESSED 的关系。
- [ ] **Step 2: 运行契约测试确认失败。**

```bash
pytest tests/test_quality_contracts.py -q
```

预期：因 `rda.quality` 契约尚不存在而失败。

- [ ] **Step 3: 实现不可变契约。** 使用 `Enum` 和 `dataclass(frozen=True)`；`UnitResult` 强制 `plan_unit_id`、四层状态、coverage 和 reason code，所有 `PASS/REVIEW/EXCLUDE_CANDIDATE` 必须具有适用且已计算的 measurement 和显式 rule ID/version；SKIPPED/FAILED/CANCELLED 必须 UNASSESSED 且带原因。EXCLUDE_CANDIDATE 还须有适用的校准来源，PASS 须满足覆盖要求；嵌套字段同样不可变。
- [ ] **Step 4: 写配置失败测试。** 覆盖缺 `contract_version`、未知 metric、quality rule 没有适用范围、已提供 training profile 但缺 horizon/stride、配置键顺序变化。robot/training profile 完全未提供合法，且不能把占位值变成真实语义。
- [ ] **Step 5: 实现规范化配置与 hash。** `QualityConfig.from_mapping` 只接受显式 schema；使用递归排序、稳定数字和 UTF-8 JSON 生成 hash；保存 requested config 和 effective config。
- [ ] **Step 6: 写 execution plan 测试。** 覆盖相同输入生成相同 ID、不同 camera/维度组生成不同 ID、计划与结果集合不一致、重复结果和缺终态。
- [ ] **Step 7: 实现 `ExecutionPlan`。** 提供 `build_plan(...)`、`validate_terminal_results(...)`、`coverage_summary(...)`；重试作为 attempt 记录，不重复发布 unit result。
- [ ] **Step 8: 运行测试并提交。**

```bash
pytest tests/test_quality_contracts.py tests/test_quality_config.py tests/test_quality_execution_plan.py -q
git add rda/quality tests/test_quality_contracts.py tests/test_quality_config.py tests/test_quality_execution_plan.py
git commit -m "feat: add RDA quality contracts and execution plan"
```

## Task 2: 补齐输入快照、LeRobot v3 episode 和媒体边界

**Files:**
- Create: `rda/quality/input_manifest.py`
- Create: `rda/quality/media.py`
- Modify: `rda/io/lerobot_loader.py`
- Test: `tests/test_quality_input_manifest.py`
- Test: `tests/test_quality_v30_boundaries.py`
- Test: `tests/test_quality_media_pts.py`

**Interfaces:**
- `load_quality_manifest(path: Path) -> QualityInputManifest`：读取已由 Adapter 生成的快照和 episode/media 索引。
- `iter_episode_segments(manifest, episode_id) -> Iterator[EpisodeSegment]`：返回该 episode 的全部 Parquet 行段，禁止单文件截断。
- `decode_media_interval(ref: MediaRef, target_times: Sequence[float], mode: str) -> Iterator[DecodedFrame]`：仅返回 `[from_timestamp, to_timestamp)` 内且真实 PTS 合法的帧。
- `EpisodeSegment` 保存源路径、row start/end、原始 timestamp 和 task 身份；`DecodedFrame` 保存目标时间、PTS、time_base、frame index、采样误差。

- [ ] **Step 1: 写 v3 边界失败测试。** 构造两个 episode 共用 Parquet/MP4，加入非零视频起点、跨文件行段、关键帧在前一段和尾部不可解码样本；断言读取不串段且缺段有终态。
- [ ] **Step 2: 运行边界测试确认失败。**

```bash
pytest tests/test_quality_v30_boundaries.py tests/test_quality_media_pts.py -q
```

- [ ] **Step 3: 实现 manifest schema。** 校验快照内容摘要、Robovet run ID、预期 episode 集、Parquet 行段、task 和相机 from/to；缺字段返回结构化输入错误。
- [ ] **Step 4: 修改 v3 loader 使用全部行段。** 读取所需列并保留原始 timestamp、frame/global index；对不支持的布局抛出 `unsupported_layout`，不合成时间轴掩盖缺失。
- [ ] **Step 5: 实现 PTS 受限解码。** seek 只作为起点；逐帧过滤目标区间，校验当前 episode 上界并返回真实 PTS；记录 attempted/computed/error 数。
- [ ] **Step 6: 写错误覆盖测试。** 覆盖缺媒体、单相机失败、跨文件 episode、输入文件被替换、空 episode、共享媒体重叠区间。
- [ ] **Step 7: 运行输入测试并提交。**

```bash
pytest tests/test_quality_input_manifest.py tests/test_quality_v30_boundaries.py tests/test_quality_media_pts.py -q
git add rda/quality/input_manifest.py rda/quality/media.py rda/io/lerobot_loader.py tests/test_quality_*
git commit -m "feat: enforce quality input and media episode boundaries"
```

## Task 3: 从读取数据生成版本化 measurement records

**Files:**
- Create: `rda/quality/measurements.py`
- Create: `rda/quality/features.py`
- Modify: `rda/metrics/motion.py`
- Modify: `rda/metrics/temporal.py`
- Modify: `rda/metrics/visual_quality.py`
- Modify: `rda/metrics/visual_integrity.py`
- Test: `tests/test_quality_measurements.py`
- Test: `tests/test_quality_motion_semantics.py`
- Test: `tests/test_quality_visual_measurements.py`

**Interfaces:**
- `MeasurementRecord(plan_unit_id, metric_name, algorithm_version, effective_config_hash, applicability, coverage, values, evidence)`：只表示已计算事实，不带业务结论。
- `compute_shared_features(episode, robot_profile) -> SharedFeatures`：输出分组动作变化、state 变化、图像变化和时间差，保留单位/维度来源。
- `measure_unit(unit, episode, media, config) -> MeasurementRecord`：只计算指定计划单元，不从默认全量指标列表隐式选择。

- [ ] **Step 1: 写运动语义失败测试。** 覆盖恒定非零速度命令、恒定位置、增量位置、周期角跨界、夹爪离散变化、混合单位和 MAD 为零的单点尖峰；断言只输出测量或正确的维度级异常证据。
- [ ] **Step 2: 写视觉测量失败测试。** 覆盖样本实际 PTS 落在 episode 外、计划 10 帧但成功 6 帧、局部模糊、短曝光和冻结区间；断言 coverage 不等于 planned count。
- [ ] **Step 3: 实现共享特征。** 有 robot profile 时按 dimension group 分开计算；无 profile 时保留原始逐维统计，物理语义和训练窗口保持 UNKNOWN/UNASSESSED；保留 action command delta、state physical delta 和 image delta；周期量使用环绕差分，离散量不求欧氏范数。
- [ ] **Step 4: 修正运动指标。** 真实 timestamp 无效时返回测量错误；MAD 零/近零采用显式退化状态；velocity/acceleration 输出单位、差分、平滑和有效样本数。
- [ ] **Step 5: 修正时序指标。** 接受 training profile 的 horizon、stride、padding 和 delta timestamp；不跨 episode 拼接；输出窗口候选引用和边界原因。
- [ ] **Step 6: 修正视觉指标。** 复用 `decode_media_interval`；输出计划样本、实际样本、PTS、相机、ROI、预处理、失败原因和最差片段；quality allowlist 必须把 `video_stream_sync`、joint_limit、schema/integrity、基础时间戳及解码验收列为 delegated；显式请求时给出结构化 UNASSESSED 原因，不运行旧算法或计入质量成功数。
- [ ] **Step 7: 串行化 measurement record。** 每个 record 必须带 algorithm/version/config hash、applicability、coverage；不填充缺失数值为 0。
- [ ] **Step 8: 运行测试并提交。**

```bash
pytest tests/test_quality_measurements.py tests/test_quality_motion_semantics.py tests/test_quality_visual_measurements.py -q
git add rda/quality rda/metrics tests/test_quality_measurements.py tests/test_quality_motion_semantics.py tests/test_quality_visual_measurements.py
git commit -m "feat: add versioned RDA quality measurements"
```

## Task 4: 让规则与校准只消费本次 measurement

**Files:**
- Create: `rda/quality/rules.py`
- Create: `rda/quality/scoring.py`
- Modify: `rda/calibration/reference.py`
- Modify: `rda/calibration/portable.py`
- Modify: `rda/calibration/scorer.py`
- Test: `tests/test_quality_rules.py`
- Test: `tests/test_quality_measurement_scoring.py`

**Interfaces:**
- `evaluate_measurement(record, rule, context) -> Assessment`：输入一个已完成 measurement，输出 `UNASSESSED / PASS / REVIEW / EXCLUDE_CANDIDATE`。
- `score_measurements(records, reference, groups) -> tuple[ScoredMeasurement, ...]`：只读取 records，不重新读取 EpisodeData。
- `RuleContext(rule_id, rule_version, applicable_scope, threshold, calibration_id)`：任何正式评估都必须引用。

- [ ] **Step 1: 写规则测试。** 覆盖无 rule 的 COMPUTED→UNASSESSED、临时启发式的 provisional REVIEW、显式校准规则的 EXCLUDE_CANDIDATE、applicability UNKNOWN、覆盖不足和规则适用范围不匹配。
- [ ] **Step 2: 写 scorer 防回归测试。** monkeypatch 旧 metric 构造器，证明 scorer 不会重新调用；传入缺 measurement 的 record，证明不会填 0；参考 MAD 为零时返回 `reference_degenerate`。
- [ ] **Step 3: 实现 metric-local rule。** 规则只访问 record.values/evidence；状态与 reason code 独立；没有 rule version 时禁止 PASS/EXCLUDE_CANDIDATE。
- [ ] **Step 4: 改造 calibration scorer。** 增加 `score_measurements`，按 robot/task/camera/dimension group 匹配 reference；缺组、维度不匹配、样本不足和零方差分别返回原因。
- [ ] **Step 5: 保留旧 calibration API 兼容。** 旧 API 继续服务 legacy audit，并在文档和类型上标记不供 quality mode 使用；quality mode 只调用新入口。
- [ ] **Step 6: 生成解释性 finding。** finding 包含 measurement、threshold、rule/calibration ID、evidence level 和定位，不生成“坏数据概率”。
- [ ] **Step 7: 运行测试并提交。**

```bash
pytest tests/test_quality_rules.py tests/test_quality_measurement_scoring.py -q
git add rda/quality rda/calibration tests/test_quality_rules.py tests/test_quality_measurement_scoring.py
git commit -m "feat: evaluate quality from current measurements"
```

## Task 5: 对齐真实训练 loader 的窗口与 policy 语义

**Files:**
- Create: `rda/quality/window_contract.py`
- Create: `rda/quality/window_diagnostics.py`
- Modify: `rda/recommend/temporal_metrics.py`（只提取可复用纯计算，不调用远程服务）
- Test: `tests/test_quality_window_contract.py`
- Test: `tests/test_quality_window_loader_parity.py`

**Interfaces:**
- `TrainingWindow(index, episode_index, observation_frames, action_frames, padding_mask, delta_t, camera_tolerance)`。
- `load_training_windows(path_or_provider, profile) -> Iterator[TrainingWindow]`：优先消费固定版本训练 loader 输出。
- `compare_window_indices(rda_windows, training_windows) -> WindowParityReport`：返回缺失、多余、边界不一致和对齐误差。
- `compute_window_diagnostics(windows, findings) -> WindowDiagnostics`：输出 `structurally_available_windows`、`active_window_ratio`、`no_detected_risk_window_ratio`。

- [ ] **Step 1: 写窗口契约失败测试。** 覆盖 delta timestamp、episode 边界、padding mask、action horizon、stride、动作/观测偏移和多相机容差。
- [ ] **Step 2: 写 loader parity 测试。** 同一 fixture 由训练 loader 和参考实现生成窗口，覆盖 episode 尾部、padding 和跨相机延迟；断言差异有具体 frame/window 定位。
- [ ] **Step 3: 实现 provider 接口。** 训练 loader 通过显式 adapter 注入；没有 provider 时参考实现结果带 `alignment=UNASSESSED`，不能冒充真实训练可用窗口。
- [ ] **Step 4: 实现差分校验。** 对 episode、observation/action 索引、padding 和相机时间容差逐项比较；不支持的采样语义返回 UNASSESSED。
- [ ] **Step 5: 实现窗口诊断。** findings 只覆盖已检测风险；输出 no-detected 名称与未检查窗口数，禁止命名为 risk-free。
- [ ] **Step 6: 运行测试并提交。**

```bash
pytest tests/test_quality_window_contract.py tests/test_quality_window_loader_parity.py -q
git add rda/quality rda/recommend tests/test_quality_window_contract.py tests/test_quality_window_loader_parity.py
git commit -m "feat: align quality windows with training loader"
```

## Task 6: 实现流式执行、预算、checkpoint 和恢复

**Files:**
- Create: `rda/quality/runner.py`
- Create: `rda/quality/checkpoint.py`
- Create: `rda/quality/resources.py`
- Modify: `rda/cli/main.py`
- Test: `tests/test_quality_runner.py`
- Test: `tests/test_quality_resume.py`
- Test: `tests/test_quality_resource_budgets.py`

**Interfaces:**
- `run_quality(request: QualityRequest) -> QualityRunSummary`：执行 quality mode 并发布 bundle。
- `CheckpointStore.load(run_key) / save_unit(unit_result) / mark_stage(stage)`：按输入快照、配置、算法、依赖和采样计划绑定。
- `ResourceBudget(max_workers, max_rss_bytes, max_cache_bytes, max_decode_workers, max_runtime_seconds, max_output_bytes, max_evidence)`。

- [ ] **Step 1: 写 runner 测试。** 覆盖单元完成顺序、失败后继续、写 staging、发布完成标记和 run_state 优先级。
- [ ] **Step 2: 写恢复测试。** 首次运行在 measurement、scoring、aggregation、publish 各阶段中断；重启只复用 hash 有效的已完成单元，最终结果与不中断运行一致。
- [ ] **Step 3: 写预算测试。** 覆盖 RSS、缓存字节、解码并发、时间、输出和 evidence 数量超限；断言结构化停止且 coverage 说明原因。
- [ ] **Step 4: 实现流式 plan executor。** 从 input manifest 流式读 episode，按所需列投影；measurement、rule、finding 和 aggregate 增量写入 JSONL/摘要。
- [ ] **Step 5: 实现共享媒体缓存。** 按字节预算控制缓存，顺序读取相同物理视频，冻结/视觉质量复用 decoded features；超过预算驱逐并记录命中率。
- [ ] **Step 6: 实现 checkpoint 和原子发布。** `execution_plan.jsonl`、unit results、staging hashes、run state 和 completed marker 分开写；发布前检查计划/结果集合完全一致。中断或预算停止时为未执行单元补终态 CANCELLED/SKIPPED；真正缺结果的 crash staging 不封口。报告封口完整性与计算覆盖分开记录；PARTIAL 表示可选计算覆盖减少，必需单元失败，或因预算/能力不足而 SKIPPED/CANCELLED（非用户停止、非前提失效）为 ERROR；前提失效为 BLOCKED，用户停止为 INTERRUPTED。
- [ ] **Step 7: 新增 CLI。** 注册 `rda audit DATASET --mode quality --config ... --input-manifest ... --run-dir ... [--resume]`，旧入口行为不变；stdout 只打印摘要，不打印完整 JSON。
- [ ] **Step 8: 运行测试并提交。**

```bash
pytest tests/test_quality_runner.py tests/test_quality_resume.py tests/test_quality_resource_budgets.py -q
git add rda/quality rda/cli/main.py tests/test_quality_runner.py tests/test_quality_resume.py tests/test_quality_resource_budgets.py
git commit -m "feat: add resumable quality execution"
```

## Task 7: 输出新版报告与质量建议，不生成训练清单

**Files:**
- Create: `rda/quality/report.py`
- Create: `rda/quality/output_bundle.py`
- Modify: `rda/report/json_report.py`（legacy 入口不改变）
- Test: `tests/test_quality_report.py`
- Test: `tests/test_quality_output_bundle.py`

**Interfaces:**
- `build_quality_report(run_summary) -> Mapping`：新版报告主版本，包含 execution_plan、四层状态、coverage、effective_config、measurement、rule advice 和限制。
- `write_quality_bundle(report, output_root) -> QualityOutputSummary`：写 `run.json`、`quality_report.json`、`episode_quality.jsonl`、`quality_advice.jsonl`、`findings.jsonl`、`not_audited.jsonl`。
- `quality_advice.jsonl` 每行包含 `rda_assessment`、来源、证据和空的 `human_decision`；不得包含名为最终训练放行的字段。

- [ ] **Step 1: 写报告 schema 测试。** 覆盖主版本拒绝、四层状态、计划/结果集合、逐指标 coverage、effective config hash、measurement→rule 链接。
- [ ] **Step 2: 写决策边界测试。** 断言报告不存在 `procurement_quality_decision` 和最终 `training_selection_decision` 的写入；`quality_advice.jsonl` 不被标为训练清单。
- [ ] **Step 3: 实现报告生成。** 对每个 plan unit 序列化 applicability、execution_state、assessment、coverage、measurement、evidence 和 reason code；聚合分母保留未评估项。
- [ ] **Step 4: 实现原子 bundle。** 写 staging、hash 和完成标记；旧 `training_selection_manifest.jsonl` 只作为 deprecated compatibility projection，内容为 quality advice。
- [ ] **Step 5: 实现 report validator。** 消费端先验证 schema、completed marker、所有 artifact hash、dataset/Robovet/RDA identities 和 run_state，再读取 JSONL。
- [ ] **Step 6: 运行测试并提交。**

```bash
pytest tests/test_quality_report.py tests/test_quality_output_bundle.py -q
git add rda/quality rda/report/json_report.py tests/test_quality_report.py tests/test_quality_output_bundle.py
git commit -m "feat: publish versioned RDA quality advice bundle"
```

## Task 8: 升级 Robovet Adapter 的 A0 契约闭环

**Files:**
- Modify: `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/worktrees/robovet-validation-a2/src/robovet/rda_adapter/contracts.py`
- Modify: `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/worktrees/robovet-validation-a2/src/robovet/rda_adapter/robovet_input.py`
- Modify: `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/worktrees/robovet-validation-a2/src/robovet/rda_adapter/rda_runner.py`
- Modify: `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/worktrees/robovet-validation-a2/src/robovet/rda_adapter/report_normalizer.py`
- Modify: `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/worktrees/robovet-validation-a2/src/robovet/rda_adapter/outputs.py`
- Modify: `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/worktrees/robovet-validation-a2/src/robovet/rda_adapter/api.py`
- Test: `.../worktrees/robovet-validation-a2/tests/rda_adapter/test_quality_protocol.py`
- Test: `.../worktrees/robovet-validation-a2/tests/rda_adapter/test_real_producer_contract.py`

**Interfaces:**
- Adapter 新协议只接受 RDA quality report 主版本和 `effective_config` hash；旧报告走显式 legacy parser。
- `RobovetContext` 提供 verified full run、可信 dataset identity、expected episode/media index 和 report hash。
- Adapter 新协议只做前置门禁、契约校验、身份映射和兼容投影；删除/禁用 `_apply_policy` 的二次质量评分。

- [ ] **Step 1: 写真实 producer fixture 测试。** 覆盖 Robovet full 模式、真实 identity 字段、inventory locator、artifact hashes、dataset 变更和报告目录重合。
- [ ] **Step 2: 写 RDA protocol 测试。** 覆盖完整配置传递、effective config 回显、未知主版本、空/缺 episode、重复/额外 episode、逐指标 not audited、合法质量退出码。
- [ ] **Step 3: 强制 full 验收和目录隔离。** 复用 verified reader；拒绝 precheck、缺必需 coverage、输出/缓存覆盖数据或 Robovet 报告目录。
- [ ] **Step 4: 实现可信 identity 与 episode 对账。** expected IDs 以已核验输入为准；RDA 不能覆盖 task、路径、Robovet 状态或 Adapter hash；结果集合差异阻止发布。
- [ ] **Step 5: 传递完整 quality config。** runner 传 config/manifest/run-dir/resume，读取并比较 RDA effective config；旧 CLI 不支持时返回明确 unsupported protocol。
- [ ] **Step 6: 扩展标准产物。** Adapter 生成 `quality_advice.jsonl` 和逐指标 `not_audited`；旧 manifest 只输出带 deprecated 标记的兼容别名；不写公司核心决定。
- [ ] **Step 7: 运行 Robovet 适配层回归并提交独立仓库。**

```bash
cd /home/fazepurple/文档/ChatGPT/lerobot数据集工具/worktrees/robovet-validation-a2
pytest tests/rda_adapter -q
git add src/robovet/rda_adapter tests/rda_adapter
git commit -m "feat: bind adapter to RDA quality protocol"
```

## Task 9: 接入 FiftyOne 展示及公司核心事件提交契约

**Files:**
- Create: `rda/integrations/__init__.py`
- Create: `rda/integrations/fiftyone_quality_import.py`
- Create: `rda/integrations/review_event_client.py`
- Create: `docs/quality-decision-integration.md`
- Test: `tests/test_fiftyone_quality_import.py`
- Test: `tests/test_review_event_client.py`

**Interfaces:**
- `import_quality_advice(bundle_root, dataset_view) -> ImportSummary`：导入 evidence、quality advice、episode/task/camera/time 定位和人工字段。
- `ReviewEventDraft`：包含 dataset snapshot、Robovet/RDA run ID、decision_type、value、reviewer、reason、policy_version、created_at、supersedes 和幂等键的不可变提交草稿。
- `submit_review_event(draft, core_client) -> CoreReceipt`：向显式注入的公司核心入口提交，区分待提交、确认保存和失败；RDA 本地草稿与 FiftyOne 字段均不构成权威记录。

**Ownership and dependency:** 公司核心仓库/服务位置仍待用户补充。权威 append-only 存储、两类决策派生和正式训练清单只能在公司核心实现，不在 RDA 创建替代服务。此任务先完成可测试的消费端与提交接口；未接入真实核心时保留明确未接入状态。外部核心实现和真实回写验证列入 release gate，不能用模拟客户端宣称完成。

- [ ] **Step 1: 写 FiftyOne import 测试。** 覆盖多相机 media refs、episode frame/time 区间、quality advice、plan unit、未评估原因和人工字段；Parquet 路径不能被误当成视频 filepath。
- [ ] **Step 2: 写事件提交测试。** 采购 ACCEPT/PENDING/REJECT 与训练 KEEP/EXCLUDE/PENDING 使用不同 decision_type；验证重复提交幂等键、保留草稿、失败重试和核心确认回执，不能在本地派生最终业务决定。
- [ ] **Step 3: 实现只读导入器。** 从已验证 bundle 导入字段与定位；重复导入保留人工字段，通过显式核心客户端提交。
- [ ] **Step 4: 实现严格草稿与回执 schema。** 强制身份、reviewer、时间、理由、policy version 和 supersedes；无核心客户端时输出 pending，不伪造成功回执。
- [ ] **Step 5: 写运行手册。** 明确权威事件不可被 RDA/FiftyOne 修改；公司核心分别生成采购与训练结论。同一 episode 可采购合格而某次训练不用。
- [ ] **Step 6: 运行消费端和事件客户端测试并提交。**

```bash
pytest tests/test_fiftyone_quality_import.py tests/test_review_event_client.py -q
git add rda/integrations docs/quality-decision-integration.md tests/test_fiftyone_quality_import.py tests/test_review_event_client.py
git commit -m "feat: integrate quality evidence and core event submission"
```

## Task 10: 完成真实链路、容量和校准验收

**Files:**
- Create: `tests/e2e/test_quality_real_chain.py`
- Create: `tests/fixtures/lerobot_v30_quality/`（仅合成数据和缺陷注入）
- Create: `docs/quality-release-checklist.md`
- Modify: `docs/quality-decision-integration.md`

**Interfaces:**
- E2E 入口：真实 Robovet producer → `robovet rda-audit` 新协议 → RDA quality mode → Adapter bundle → FiftyOne import → event submission client。当前合成客户端仅验证提交契约；接入真实公司核心、权威记录和两类决策为外部 release acceptance。
- Release checklist 记录 schema、覆盖、资源、恢复、输入不可变、许可证/依赖、人工决定和训练清单来源。

- [ ] **Step 1: 构造合成 v3 fixture。** 至少两个 episode 共用 Parquet/MP4，包含正常、静止、动作尖峰、视频冻结、模糊、曝光、缺片段、跨边界和多相机样本。
- [ ] **Step 2: 运行真实 Robovet full 验收。** 保存 verified identity、episode/media index 和 artifact hashes；故障 fixture 必须被前置门禁阻断。
- [ ] **Step 3: 运行真实 RDA quality CLI。** 改变质量 profile、训练窗口和采样计划，确认 effective config 和 measurement/coverage 随配置变化；确认不调用网络。无真实固定版本 trainer 时只验证配置传播、窗口输入契约和 UNASSESSED 分支，不宣称 loader parity。
- [ ] **Step 4: 运行 Adapter 与 FiftyOne 集成。** 验证 quality advice 可定位、人工草稿经显式客户端提交、重复导入不覆盖人工字段。合成客户端不能证明公司核心持久化；真实核心回写、幂等权威历史及正式训练清单归属单列为尚待接入的 release gate。
- [ ] **Step 5: 做中断恢复与资源压测。** 记录峰值 RSS、缓存、解码次数、输出大小、耗时、worker 数；在每个 checkpoint 阶段中断并核对复跑结果。
- [ ] **Step 6: 做真实数据准备验收。** 收集真实机器人 profile、相机配置、任务映射、目标 loader、人工参考样本和容量目标；在资料齐全前不启用正式阈值或 EXCLUDE_CANDIDATE。
- [ ] **Step 7: 更新 release checklist 并提交。**

```bash
pytest tests/test_quality_* tests/e2e/test_quality_real_chain.py -q
git add tests/e2e tests/fixtures docs/quality-release-checklist.md docs/quality-decision-integration.md
git commit -m "test: verify end to end quality chain"
```

## Task 11: 补齐 R5 分组分布、显式任务映射与固定边界覆盖

**Files:** `rda/quality/distribution.py`、`rda/quality/coverage.py`、`tests/test_quality_distribution.py`、`tests/test_quality_coverage.py`。

**Interfaces:** 增量可合并的 grouped summaries；显式 task mapping（保留原始 task_index/task 和版本）；固定维度、单位、坐标系、边界与 bins 的 coverage 配置。

- [ ] **Step 1: 先写失败测试。** 同一动作区域在不同 episode 中应落同一固定网格；缺目标清单仅 observed distribution；有目标时才报告缺失/样本不足任务；缺 reference 组不能判坏数据。
- [ ] **Step 2: 实现分组统计。** 按已核验输入的 robot/task/camera/source 及动作表示分组，输出 episode 数、时长、已测活动时长、四层状态计数、逐维范围和参考偏离，缺失标签为 unknown。
- [ ] **Step 3: 实现任务映射和覆盖。** 原值永不覆盖；显式映射进入配置 hash。不使用每个 episode 自身 min/max 来报告全局工作空间覆盖。无固定边界或语义不足时 UNASSESSED；局部占用单独命名。
- [ ] **Step 4: 验证合并摘要不重复 episode，参考身份/维度/单位不匹配有明确原因，提交。**

## Task 12: 补齐 capabilities、最小安装依赖和干净环境验证

**Files:** `rda/quality/capabilities.py`、`rda/cli/main.py`、`pyproject.toml`、`requirements-quality.lock`、`tests/test_quality_capabilities.py`、`docs/quality-installation.md`。

- [ ] **Step 1: 先写 capabilities 失败测试。** 声明 quality 协议主版本、配置 schema、算法版本、delegated checks、PyAV/Parquet/provider 可用性；不导入训练栈或触发网络下载。
- [ ] **Step 2: 实现 `rda capabilities --format json`。** 无可选依赖仍能报告缺项；对应计划单元返回原因。
- [ ] **Step 3: 定义最小 quality extra、视觉 extra 和有生成方法的锁定文件。** 包含 pandas/pyarrow 和实际运行依赖；PyAV 可独立启用。禁止强制安装 Streamlit、训练栈或模型权重。
- [ ] **Step 4: 干净虚拟环境安装并验证 capabilities、quality CLI、Parquet 读取及 H.264 合成视频解码；记录 Python、依赖、FFmpeg 和安装平台边界，提交。**

## Task 13: Robovet producer 验收时绑定内容快照与读取索引

**Worktree:** `/home/fazepurple/文档/ChatGPT/lerobot数据集工具/worktrees/robovet-validation-a2`（独立仓库）。

**Files:** `src/robovet/validation/` 中 discovery/evidence/pipeline 的最小证据扩展；必要的新 snapshot/index 模块；`tests/validation/test_snapshot_binding.py`；真实 producer 契约 fixture。

- [ ] **Step 1: 先写验收绑定失败测试。** 正式验收前后内容替换、运行中源变化、缺少旧报告绑定、共享文件/跨文件行段、真实 inventory 字段、部分验收不能冒充 full。
- [ ] **Step 2: 在验收运行同时产生内容清单与 episode/media 索引。** 明确快照保证方式，绑定 scope、全文件内容摘要、Robovet run ID、原始 task 及所有行段/视频区间，不用事后 hash 追认历史报告。可采用验收前后内容核对并如实标识保证级别；不能声称不可变文件系统。
- [ ] **Step 3: 将清单纳入已核验产物 hash。** 运行中变更应使绑定不可消费。旧报告缺绑定时 Adapter 新模式必须 BLOCKED，要求重新 full 验收。
- [ ] **Step 4: 运行 Robovet validation 和 adapter legacy 回归并独立提交。** 不迁移质量算法进入 producer。

## Implementation order and review gates

1. Task 1 必须先完成；它定义的四层状态、`PlanUnit`、`MeasurementRecord` 和配置 hash 是后续所有任务的接口。
2. Task 2 完成后才允许开发视觉和窗口逻辑；否则共享文件和视频边界问题会污染所有 measurement。
3. Task 3 与 Task 4 必须连续评审；Task 4 不得通过旧 calibration API 绕过 Task 3 的 measurement record。
4. Task 5 需要真实训练 loader 的固定版本；在 loader 尚未提供前只能完成参考实现、差分契约和 UNASSESSED 路径。
5. Task 11 接在 Task 5 后、报告之前；Task 6、Task 7 形成一个发布单元；没有 completed marker、全量 plan unit 终态和 hash 校验不能交给 Adapter。
6. Task 12 在 Task 7 后完成；Task 13 是 Task 8 的 producer 前置，先通过再接新协议。Adapter 的 legacy 路径继续回归。执行顺序为 1→2→3→4→5→11→6→7→12→13→8→9→10。
7. Task 9 明确公司核心事件和两类决策的权威归属；没有该接口，`quality_advice.jsonl` 不得改名或包装成正式训练清单。
8. Task 10 的代码/合成验证和外部真实验收分别报告；真实 release gates（核心、trainer、数据与标定）满足后才可评价首版企业内部可用性。真实阈值、误报/漏报、容量和训练收益属于 R8 后续校准，不由合成 fixture 代替。

## Plan self-review checklist

- [x] Robovet 基础验收、RDA 质量分析、Adapter 衔接、FiftyOne 复核和公司核心决策已分开。
- [x] 采购质量结论和训练选择结论可以针对同一 episode 产生不同结果。
- [x] `quality_advice.jsonl` 与正式训练清单已分离，旧 manifest 仅兼容。
- [x] `applicability`、`execution_state`、`assessment`、`run_state` 和 `plan_unit_id` 已分配实现任务。
- [x] measurement → metric-local rule → company decision 已分配独立接口和测试。
- [x] 训练窗口要求真实 loader 优先、差分一致性测试和不支持语义的 UNASSESSED。
- [x] 共享 Parquet/视频边界、PTS、缺失 episode、部分覆盖、恢复、预算和输入替换都有测试任务。
- [x] 未把真实数据、真实阈值、分布式部署或训练收益写成当前已完成内容。

## Execution clarification — 2026-09-10

本次修订依据已确认设计和用户明确边界，补齐计划遗漏，不增加产品化平台范围。缺真实数据、机器人 profile、训练 loader 或公司核心接入不阻止可独立模块开发；相关真实验收明确为待满足的外部条件。阶段性实现、合成验证和真实内部投产验收分别记录，禁止混报完成。

状态合法性：measurement 只可附于 COMPUTED；UNKNOWN + COMPUTED 可保留已观测原始事实，但必须有适用性未知原因且 UNASSESSED。NOT_APPLICABLE 不附带伪测量。没有规则时 UNASSESSED。有版本规则才可 REVIEW，已校准适用规则及足够覆盖才可 PASS/EXCLUDE_CANDIDATE。UNKNOWN/NOT_APPLICABLE 必须 UNASSESSED；SKIPPED/FAILED/CANCELLED 不携带 measurement 且必须 UNASSESSED；失败、跳过、取消均有原因。部分有效测量保留实际 coverage，不将缺样本填零。封口不等于计算覆盖完整，更不等于质量通过。
