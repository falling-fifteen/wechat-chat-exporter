# Contributing

感谢参与。请先阅读 [README](README.md) 和 [SECURITY](SECURITY.md)。

## 开发环境

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[all,dev]"
ruff format --check src tests
ruff check src tests
mypy src
pytest -m "not realdata"
```

## 代码准则

- Python 3.10+，`from __future__ import annotations`。
- 新功能要有测试；测试只能用**合成数据**。
- 不要把真实 `*.db`、`*.db-wal`、`*.db-shm`、密钥、导出结果提交进仓库。
- 错误信息不要包含消息正文、密钥或完整隐私路径。
- 新增依赖优先选择 MIT/BSD；GPL/AGPL 依赖需要先讨论。
- 导出器实现 `Exporter` 协议，不要在 CLI 里写格式分支。

## Clean-room 规则

本项目是 MIT，参考过其他开源项目的**事实性 schema 和文件格式知识**，
但不复制其 GPL 代码。提交时请确保：

- 没有复制粘贴 GPL 项目的函数、注释、变量命名或文件结构；
- 新实现基于公开格式规范和独立编写；
- 如引用事实来源，记录在 `THIRD_PARTY.md` 或 PR 描述里。

## 提交

- 一个 PR 聚焦一件事。
- 提交信息用祈使句，例如 `fix: handle empty msg table`。
- CI 必须通过（ruff / mypy / pytest）。
- 涉及安全或隐私的改动请在 PR 描述里说明影响。
