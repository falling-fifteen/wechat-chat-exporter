# 格式与数据结构

> 本文只记录公开的文件格式和数据库 schema 事实，用于实现与排错。
> 项目未复制任何 GPL 项目的代码。

## 目录

```text
<account>/db_storage/
├─ message/
│  ├─ message_0.db
│  ├─ message_1.db
│  └─ message_2.db      # 按时间分片
├─ session/session.db
└─ contact/contact.db
```

## SQLCipher 4 页格式

- page size: 4096
- reserve: 80 = 16 字节 IV + 64 字节 HMAC-SHA512
- page 0: `[salt 16][ciphertext 4000][IV 16][HMAC 64]`
- 其他页: `[ciphertext 4016][IV 16][HMAC 64]`
- 派生：`enc_key = PBKDF2-HMAC-SHA512(key, salt, 256000, 32)`
- HMAC key：`PBKDF2-HMAC-SHA512(enc_key, salt ^ 0x3a, 2, 32)`

解密时每页补回 80 字节 reserve 区，保证 SQLite 页对齐。

## 消息表

表名：`Msg_` + `md5(username)`（32 位小写十六进制）。

关键列：

```sql
local_id, server_id, local_type, sort_seq, real_sender_id,
create_time, message_content, compress_content, packed_info_data
```

- `create_time`：Unix 秒
- `sort_seq`：毫秒级排序键
- `local_id`：分片内自增；跨分片排序要结合 `create_time`/`sort_seq`
- `real_sender_id`：指向同一分片的 `Name2Id.rowid`

## Name2Id

```sql
CREATE TABLE Name2Id(user_name TEXT);
-- real_sender_id -> Name2Id.rowid -> user_name
```

**每个分片的 rowid 映射不同**，必须按分片分别读取。这是跨库导出最容易踩的坑。

## local_type

低 32 位是基础类型，高 32 位是子类型：

| base | 含义 |
|---|---|
| 1 | 文字 |
| 3 | 图片 |
| 34 | 语音 |
| 43 | 视频 |
| 47 | 表情 |
| 49 | appmsg（链接/文件/引用/转发/小程序/红包/转账…） |
| 50 | 通话 |
| 10000 | 系统 |

例如 `244813135921 = (57 << 32) | 49`，是 appmsg 的“引用”子类型。

## 内容编码

- 普通文本：UTF-8
- 长文本/部分消息：zstd，magic `28 b5 2f fd`；可能以 bytes 或 hex 字符串出现
- appmsg：XML，`<appmsg><type>...<title>...<des>...<url>...`

## 图片 `.dat`

- 已是 JPEG/PNG/GIF/WebP/BMP：直接使用
- `07 08 56 31 08 07`：旧容器，XOR 兜底
- `07 08 56 32 08 07`：AES-XOR 容器
  - 6 字节 magic + 4 字节 `aes_size` + 4 字节 `xor_size` + 1 字节 + body
  - AES 段用 AES-128-ECB，PKCS#7 去填充；尾部 `xor_size` 字节做单字节 XOR
- `WXGF`：扫描内嵌图片签名

图片 key 优先取消息 XML 的 `aeskey`，其次取 `--image-key-file`。
