# Changelog

## 未发布

- docs: 公告项目现状——「自动获取密钥」方向暂停（上游 `wx_key` 于 2026-11-06 被
  DMCA 下架且无可用许可证）；本项目保持只支持手动提供密钥

## 0.2.2

- refactor(gui): 所有说明集中到右上角「使用说明 / Q&A」多标签窗口
- refactor(gui): 三步式布局（数据与密钥 / 选择会话 / 导出）
- feat(gui): 密钥来源改为单选（密钥文件 / 直接粘贴），只显示当前模式控件
- feat(gui): 会话搜索、全选、清空、已选数量
- feat(gui): 日志默认收起，出错自动展开
- feat(gui): 导出前确认、WAL 提示、按会话容错、部分完成报告
- feat(gui): F1/F5/Ctrl+Enter 快捷键、高 DPI、窗口居中、原生主题
- fix(gui): 空闲时不再显示进度条残影
- fix(gui): 加载失败时清理临时明文目录

## 0.2.1

- feat(gui): 数据目录说明文字 + 「自动查找数据目录」按钮
- feat(gui): 支持直接粘贴 64 位密钥，不再强制要求密钥文件
- feat(gui): 密钥说明弹窗，解释密钥是什么、如何获得
- docs: 新增 `docs/getting-key.md`

## 0.2.0

- feat: `wce gui` Tkinter 桌面界面
  - 选择数据目录/密钥/输出目录
  - 读取会话、多选、按格式导出
  - 可选最新 N 条、进度状态、日志、打开输出目录
  - 支持 `--config wce.json` 预填
- 复用 CLI 同一套解密/查询/导出代码，GUI 不引入新的数据处理逻辑

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
