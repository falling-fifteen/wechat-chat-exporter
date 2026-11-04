# Changelog

## 0.1.2

- feat: `wce.json` 配置文件，所有路径/格式/会话只写一次
- feat: `wce init` 交互式生成配置
- feat: 不传 `--config` 时自动读取当前目录 `wce.json`；CLI 参数优先
- docs: 明确所有路径都是参数，补充单命令导出示例

## 0.1.1

- fix: SQLCipher 4 HMAC 输入格式（ciphertext + IV + 1-based LE 页号，第 0 页不含 salt）
- fix: 只把 `message_<数字>.db` 当作消息分片，排除 `message_fts.db` / `message_resource.db`
- fix: `placeholder` 图片模式不再尝试解密
- fix: `file` 图片模式在 HTML 中写出 `images/` 并引用相对路径
- fix: `--since/--until` 按 `--timezone` 计算边界
- fix: DOCX 中文字体设置的空值保护
- test: Ubuntu CI 直接加载 `libsqlite3.so.0`，不依赖 `find_library`

## 0.1.0

- 首个公开版本：SQLCipher 4 解密、跨分片合并、CSV/Excel/HTML/PDF/Word/JSONL
- 单会话 / 会话列表 / 全部会话，`--limit`、日期范围、按月/年拆分
- 图片 V3 XOR / V4 AES / WXGF 基础支持，可选 image key
- 19 个合成夹具测试，MIT 许可
