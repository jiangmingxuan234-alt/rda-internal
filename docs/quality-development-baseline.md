# Quality implementation baseline — 2026-09-10

本记录只证明开发基线回归通过，不表示新质量链路或真实数据验收完成。

- RDA implementation worktree 起点：`8e883f5`，包含现有功能基线 `e998aed` 和已确认设计/实施计划。
- Robovet producer/Adapter 起点：`1bec23b35ab0546c95ff4bec98653920016c85cf`，开始前工作区干净。
- RDA 原有测试：153 passed, 6 skipped。跳过项依赖真实 LIBERO/LeRobot 数据（3 项）或 Streamlit（3 项）。
- Robovet validation + Adapter：302 passed。

可复现命令（从对应仓库运行，以实际虚拟环境路径替换 Python）：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest -q -rs
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src:tests/rda_adapter /tmp/rda-quality-venv/bin/python -m pytest tests/validation tests/rda_adapter -q -rs
```

显式 PYTHONPATH 及禁用自动插件用于隔离主机 ROS 环境注入；不代表缺少项目依赖时也能通过。后续修改需重复覆盖改动涉及的 legacy 回归。真实训练 loader、真实公司核心及采购样本仍是独立验收条件。

## Environment

Python: 3.10.12
Platform: Linux-6.8.0-138-generic-x86_64-with-glibc2.35

- numpy: 2.2.6
- pandas: 2.3.3
- pyarrow: 25.0.1
- pytest: 8.4.2
- click: 8.5.0
- pydantic: 2.13.5
- av: 16.1.0
- typer: 0.27.2
- PyYAML: 6.0.3
- psutil: 7.2.2
- requests: 2.34.2

Use PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and explicit PYTHONPATH to prevent unrelated ROS environment injection. Venv: /tmp/rda-quality-venv
RDA legacy: 153 passed, 6 skipped. Robovet validation + adapter: 302 passed.
