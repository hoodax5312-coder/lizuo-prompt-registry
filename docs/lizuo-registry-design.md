# 栗作提示词聚合仓库设计

## 目标

为栗作 LIZUO 提供独立、公开、可审计的图片提示词聚合仓库，将不同开源来源转换为稳定的标准 JSON，避免栗作客户端直接解析每个上游仓库。

## 架构

1. `sources.json` 登记来源、适配器、上游地址、主页和最低条目数。
2. `prompt_registry/parsers.py` 只处理来源差异。
3. `prompt_registry/models.py` 生成稳定 ID 和统一字段。
4. JSON Schema 在替换发布数据前验证全部记录。
5. `dist/manifest.json` 发布来源数量、路径和 SHA-256；`dist/sources/` 发布独立来源数据。
6. GitHub Actions 每日运行测试和同步，仅在有效内容变化时提交。

## 稳定性边界

- 任一来源抓取失败、解析失败、Schema 失败或条目数异常时，不覆盖上一版有效 `dist`。
- 图片只保存远程 URL，不复制第三方图片。
- 每条记录保留 `sourceId`、`author` 和 `sourceUrl`。
- 聚合仓库的 MIT License 不重新许可第三方提示词和图片。

## 与栗作的连接

栗作本机 Node 网关读取 `dist/manifest.json`，按启用来源拉取对应 JSON 并在本地缓存。设置页管理来源启停与手动同步；案例页只消费标准记录，不感知上游解析器。

## 第一阶段验收

- 公开仓库可访问。
- `pytest` 全部通过。
- 联网 `python -m prompt_registry --check` 通过。
- `dist/manifest.json` 与各来源 JSON 可由 GitHub Raw 读取。
- README 和 NOTICE 明确栗作维护关系、上游来源及版权边界。
