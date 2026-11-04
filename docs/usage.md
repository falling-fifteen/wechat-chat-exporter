# 使用说明

## 子命令

### doctor

检查数据目录、密钥、分片、WAL 和会话数量。不会写任何导出文件。

```bash
wechat-chat-exporter doctor --db-dir "D:\...\db_storage" --key-file key.txt
```

输出示例：

```text
db_storage: D:\WeChat Files\xwechat_files\wxid_xxx_c872\db_storage
账号: wxid_xxx
消息分片: 3
  - message_0.db  288.3 MB
  - message_1.db   48.2 MB
  - message_2.db   59.6 MB
WAL: 无未提交内容
解密: 3 个消息分片成功
会话: 686
有消息的会话: 681
```

### sessions

列出有消息的会话，默认按最后消息时间倒序。

```bash
wechat-chat-exporter sessions --db-dir ... --key-file key.txt
wechat-chat-exporter sessions ... --json > sessions.json
```

### export

```bash
wechat-chat-exporter export ^
  --db-dir "D:\...\db_storage" ^
  --key-file key.txt ^
  --session wxid_xxx ^
  --formats csv,xlsx,html,pdf,docx ^
  --split month ^
  --out out\chat
```

关键参数：

| 参数 | 说明 |
|---|---|
| `--session` | wxid、`@chatroom`、备注名、`all`、或每行一个会话的文件 |
| `--formats` | `csv,xlsx,html,pdf,docx,jsonl`，逗号分隔 |
| `--split` | `auto`（默认）、`none`、`year`、`month`；auto 时文档格式按月、表格不拆 |
| `--limit N` | 只导出最新 N 条（先应用 `--since/--until`） |
| `--since/--until` | `YYYY-MM-DD`，含边界；`--until` 包含当天 |
| `--timezone` | 如 `Asia/Shanghai`，影响按天/月分组和日期过滤 |
| `--me` | 自己的 wxid；默认从账号目录名推导 |
| `--label-me` | “我”的显示名，默认 `我` |
| `--exclude-system` | 不导出系统消息 |
| `--image-mode` | `none`、`placeholder`、`auto`（默认）、`inline`、`file` |
| `--image-key-file` | 可选 image key JSON |
| `--pdf-font` | 指定中文 TTF/TTC 字体 |
| `--overwrite` | `skip`（默认）、`force`、`ask` |
| `--strict-wal` | 存在未 checkpoint 的 WAL 时直接失败 |
| `--dry-run` | 只统计条数，不写文件 |
| `--keep-work` | 保留解密临时目录（含明文数据库，谨慎使用） |

### validate

检查每个 `manifest.json` 里记录的文件是否存在且非空，可选校验总条数。

```bash
wechat-chat-exporter validate --out out\chat --expect-count 107941
wechat-chat-exporter validate --out out\chat --json
```

## 会话选择

```bash
# 精确 wxid
--session wxid_abcd1234

# 群聊
--session 123456789@chatroom

# 备注名（唯一匹配时）
--session "女朋友"

# 全部有消息的会话
--session all

# 会话列表文件
--session sessions.txt
```

备注名匹配到多个会话时会报错并列出候选，请改用 wxid。

## 输出目录

- 单个会话：直接写到 `--out`
- 多个会话：每个会话一个子目录，目录名是清洗后的备注名/wxid
- 每次导出都会写 `manifest.json`，记录条数、文件大小、SHA-256 和错误

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | 参数错误 |
| 3 | 密钥/解密/表结构错误 |
| 4 | 部分会话或校验失败，结果仍可用 |
| 5 | 全部失败 |
| 130 | 用户取消 |
