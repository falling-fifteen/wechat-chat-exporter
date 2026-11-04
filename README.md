# wechat-chat-exporter

把**你自己的**微信 4.x 本地聊天记录完整导出为 CSV / Excel / HTML / PDF / Word。

A local-first CLI that exports your own WeChat 4.x chat history to CSV, Excel,
HTML, PDF and Word. It reads the decrypted databases directly, merges every
`message_*.db` shard, and therefore does **not** suffer from the 2400-message
limit of DLL-based exporters. You provide the database key yourself; the tool
never extracts keys from the WeChat process.

> 非官方项目，与腾讯 / 微信没有任何关联。Not affiliated with Tencent.

## 为什么做这个

很多现成的微信导出工具依赖一个封装好的 DLL，单次查询最多返回 2400 条消息，
而且 GUI 永远只请求第一页，长会话只能导出最近 2400 条。

这个项目换了一条路：**用你提供的密钥直接解密 `message_0/1/2.db` 等全部分片，
在 SQLite 里跨库合并后再导出**。实测一个 107,941 条的会话可以完整导出，首尾时间
与微信客户端一致。

## 功能

- 跨分片全量合并，不是“最新 2400 条”
- 文字、引用/链接/文件等 appmsg 卡片、系统消息
- 图片内嵌（`.dat` V3 XOR / V4 AES / WXGF 基础处理）
- CSV / Excel / HTML / PDF / Word / JSONL
- 单会话、指定会话列表、全部会话批量导出
- 群聊（发送者按 `Name2Id` + `contact.db` 尽力解析）
- 最新 N 条（`--limit`）、日期范围（`--since/--until`）
- 按月 / 按年拆分，避免单个文件过大
- 临时明文目录默认自动清理

## 重要声明

- 仅用于导出**你本人**的数据，或你已获得明确授权的数据。
- 本工具**不提供**密钥提取、内存扫描、DLL 注入或任何绕过微信登录/保护的功能。
  你需要自己合法持有数据库密钥。
- 导出他人聊天记录可能违反当地法律、平台条款和聊天参与者隐私，请自行确认授权。
- 软件按 MIT “AS IS” 提供，不承担数据丢失或法律责任。

## 已验证环境

- Windows 11，微信 **4.2.0.11**
- Python 3.10 – 3.13
- 其他微信 4.x 版本为尽力兼容；`doctor` 会给出明确的失败原因

## 安装

```bash
git clone https://github.com/falling-fifteen/wechat-chat-exporter.git
cd wechat-chat-exporter
python -m venv .venv
.venv\Scripts\pip install -e ".[all]"
```

可选依赖分组：`[excel]`、`[pdf]`、`[docx]`、`[images]`、`[all]`。

## 快速开始

所有路径都是参数，代码里没有写死任何用户目录。最省事的方式是先把路径写进
`wce.json`，之后一条命令就能导出：

```bash
# 交互式生成配置（只问一次路径）
wechat-chat-exporter init

# 之后只需要这一条
wechat-chat-exporter export --config wce.json
```

也可以把它当成普通 CLI，用参数直接指定：

```bash
wechat-chat-exporter export ^
  --db-dir "D:\WeChat Files\xwechat_files\wxid_xxx_c872\db_storage" ^
  --key-file key.txt ^
  --session all ^
  --formats csv,html,pdf,docx ^
  --out out\chat
```

`doctor` 和 `sessions` 是可选的诊断工具：

```bash
# 体检：验证密钥、列出分片、检测未 checkpoint 的 WAL
wechat-chat-exporter doctor ^
  --db-dir "D:\WeChat Files\xwechat_files\wxid_xxx_c872\db_storage" ^
  --key-file key.txt

# 列出有消息的会话
wechat-chat-exporter sessions --db-dir ... --key-file key.txt

# 单个会话全量，五种格式，按月拆分
wechat-chat-exporter export ^
  --db-dir ... --key-file key.txt ^
  --session wxid_xxx ^
  --formats csv,xlsx,html,pdf,docx ^
  --split month ^
  --out out\chat

# 只导出最近 5000 条，或某个日期范围
wechat-chat-exporter export ... --limit 5000
wechat-chat-exporter export ... --since 2025-01-01 --until 2025-12-31

# 批量导出全部会话
wechat-chat-exporter export ... --session all --formats csv,html --out out\all

# 校验结果
wechat-chat-exporter validate --out out\chat --expect-count 107941
```

短命令 `wce` 与 `wechat-chat-exporter` 等价。

## 图形界面

不想敲命令的话：

```bash
wce gui
```

界面里依次选择：

1. 微信数据目录（`db_storage` 或其上级目录）
2. 密钥文件
3. 输出目录
4. 点 **读取会话**，等列表加载
5. 选中一个或多个会话，勾选格式
6. 点 **开始导出**

可选的「最新条数」留空表示导出全部。导出完成后会提示输出目录，也可以点
**打开输出目录**。GUI 使用 Python 自带的 Tkinter；Linux 上如果缺失，安装
`python3-tk` 即可。

## 密钥怎么提供

密钥必须由你自己提供，工具不会去微信进程里读：

```bash
# 推荐：文件（内容为 64 位十六进制）
wechat-chat-exporter export ... --key-file key.txt

# 或环境变量
set WECHAT_CHAT_EXPORTER_KEY=<64-hex>
wechat-chat-exporter export ...

# 或从 stdin / 交互输入
wechat-chat-exporter export ... --key-stdin
```

命令行**不接受**明文 `--key` 参数，日志和错误信息也会自动脱敏。

GUI 里除了选择密钥文件，也可以直接把 64 位密钥粘贴到输入框，不需要先建文件。
如果你还没有密钥，请先看 [docs/getting-key.md](docs/getting-key.md)。

## 图片密钥（可选）

图片 `.dat` 有时需要账号级 image key。工具会先尝试消息 XML 里的 `aeskey`；
失败时再使用 `--image-key-file` 指定的 JSON。没有密钥时图片降级为 `[图片]` 占位，
不会中断导出。

支持两种格式：

```json
{
  "account": "wxid_xxx",
  "xor_key": 0,
  "aes_key_hex": "00112233445566778899aabbccddeeff"
}
```

也兼容常见的 `{"accounts":[{"wxid":"...","keys":[{"code":123}]}]}` 形状。

## 输出

```text
out/chat/
├─ 文件传输助手.csv
├─ 文件传输助手.xlsx
├─ 文件传输助手_2025-09.html
├─ 文件传输助手_2025-09.pdf
├─ 文件传输助手_2025-09.docx
├─ ...
└─ manifest.json      # 条数、文件、SHA-256、警告
```

- CSV / XLSX / JSONL 默认不拆分；HTML / PDF / DOCX 默认按月拆分。
- 重复运行默认 `--overwrite skip`，不会覆盖已有文件。
- CSV 会转义以 `= + - @` 开头的内容，防止公式注入。

## 已知限制

- **WAL**：如果 `message_*.db-wal` 非空，最新几条消息可能只在 WAL 里。v0.1 会检测并
  警告（`--strict-wal` 可直接失败），但还没有重放 WAL；建议先退出微信再导出。
- 语音、视频、表情包目前只输出占位符，不做 Silk/视频解码。
- 群昵称解析是 best-effort：优先 `contact.db` 的备注/昵称，解析不到就显示 wxid。
- 仅支持 SQLCipher 4（page size 4096、reserve 80）。其他参数会明确报错。
- 微信升级可能改变 schema；`doctor` 会输出可诊断的信息。

## 隐私

- 完全本地处理，无网络请求、无遥测、无自动更新。
- 解密后的明文数据库放在系统临时目录，程序结束自动删除；`--keep-work` 才会保留。
- 日志只记录计数和错误码，不记录消息正文或完整密钥。
- 导出文件本身是明文，请自行加密保管。
- 详见 [docs/privacy.md](docs/privacy.md)。

## 开发

```bash
pip install -e ".[all,dev]"
ruff format --check src tests
ruff check src tests
mypy src
pytest -m "not realdata"
```

测试使用**运行时生成的合成 SQLCipher 数据库**，不包含任何真实聊天数据。
真实数据回归通过环境变量本地执行，不进入 CI。

## 许可证

MIT。第三方依赖与来源说明见 [THIRD_PARTY.md](THIRD_PARTY.md)。
本项目未复制任何 GPL 项目的代码，只参考了公开的数据库 schema 与文件格式事实。
