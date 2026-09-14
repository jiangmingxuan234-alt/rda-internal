# Quality 安装说明

质量分析的最小依赖是 `pip install -e '.[quality]'`，其中包含 pandas 和
PyArrow，用于读取 LeRobot v3 Parquet。需要视频逐帧检查时使用
`pip install -e '.[quality-video]'`，额外安装 PyAV 及其系统 FFmpeg 库。

质量模式不会强制安装 LeRobot 训练栈、Streamlit、模型权重或联网服务。运行
`rda capabilities --format json` 可在离线环境查看实际可用能力；缺失可选包会
明确报告为 unavailable，对应检查保持未评估。

锁定版本参考 `requirements-quality.lock`。该文件记录 Linux/Python 3.10 基线，
不同 Python、操作系统或 FFmpeg 构建可能需要重新生成锁文件并执行合成视频解码验证。
