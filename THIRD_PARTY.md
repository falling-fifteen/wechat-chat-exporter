# Third-party notices

本项目以 MIT 许可证发布。以下是运行时和开发依赖，均通过包管理器安装，不随仓库分发二进制。

| 依赖 | 用途 | 许可证 |
|---|---|---|
| PyCryptodome | SQLCipher / 图片 AES | BSD-2-Clause |
| zstandard | zstd 解压 | BSD-3-Clause |
| openpyxl | Excel 导出（可选） | MIT |
| fpdf2 | PDF 导出（可选） | LGPL-3.0 |
| python-docx | Word 导出（可选） | MIT |
| Pillow | 图片处理（可选，经 fpdf2 间接使用） | HPND / MIT-CMU |
| pytest / pytest-cov | 测试 | MIT |
| ruff | lint/format | MIT |
| mypy | 类型检查 | MIT |
| build / twine | 打包发布 | MIT / Apache-2.0 |

fpdf2 是 LGPL-3.0：本项目只通过 Python import 使用它，不修改、不静态链接。
如果重新分发包含 fpdf2 的打包产物，请遵守 LGPL 的声明与可替换要求。

## 参考的事实来源

以下资料仅用于核对公开的文件格式、SQLCipher 页结构和微信 4.x 数据库 schema，
**没有复制其代码**：

- SQLCipher 4 页格式与 KDF 参数的公开实现说明
- 微信 4.x `Msg_<md5>`、`Name2Id`、`SessionTable` 等 schema 的逆向工程笔记
- 微信 `.dat` 图片容器（V3 XOR / V4 AES / WXGF）的公开格式描述
- 本地原型脚本 `decrypt_sqlcipher4.py`、`export_chat.py`（本项目作者原创）

## 不分发的内容

本项目**不包含**、也不要求用户安装：

- 腾讯 WCDB / `wcdb_api.dll`
- `wx_key.dll` 或任何密钥提取/注入工具
- 微信客户端、Electron、ffmpeg
- 任何真实聊天数据库、密钥或导出结果

“WeChat / 微信”是其权利人的商标，本项目仅为描述性使用，与腾讯无关联。
