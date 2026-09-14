# RDA 内部质量链路发布验收清单

此清单用于内部研发版本。合成测试只能证明组件契约能够串联，不能替代真实采购数据验收。

## 代码与合成测试覆盖

- [ ] 输入 manifest、LeRobot v3 行段和视频边界生成可追溯 measurement。
- [ ] 每个 `plan_unit_id` 恰好产生一个终态；失败、跳过和取消不会伪造完成标记。
- [ ] 规则建议输出 `quality_advice.jsonl`，并带规则、校准和证据 provenance。
- [ ] FiftyOne 投影只展示证据并采集 review event，不保存采购或训练最终决定。
- [ ] review event 为 append-only，采购质量结论与训练选择结论分别由公司核心生成。
- [ ] 输出包包含 `report.json`、`quality_advice.jsonl` 和校验摘要。

## 外部发布门槛（当前未验证）

- [ ] 使用供应商真实 LeRobot v3 数据完成完整性、视频逐帧和跨文件时间映射验收。
- [ ] 提供并冻结真实机器人 profile、动作字段语义、单位、坐标系、标定和关节限位。
- [ ] 用固定版本的实际 LeRobot/Cosmos loader 做窗口差分 parity；不支持的采样语义保持 `UNASSESSED`。
- [ ] 用公司批准的参考数据完成阈值校准，并审核样本量、scope、维度和 calibration hash。
- [ ] 在目标规模上完成并发、断点恢复、磁盘和内存压测，记录可复现容量指标。
- [ ] 在生产沙箱/权限环境验证隔离执行、依赖锁定和审计留痕。
- [ ] 公司核心接入真实 review event，并分别落库 procurement quality decision 与 training selection decision。

在所有外部门槛完成前，版本只能标记为“内部合成验证版”，不能宣称真实数据质量、训练收益或生产级隔离已验收。
