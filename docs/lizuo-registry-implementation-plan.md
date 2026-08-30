# LIZUO Prompt Registry Implementation Plan

**Goal:** 建立栗作独立维护、可自动同步和发布标准提示词 JSON 的公开仓库。

**Architecture:** 复用经过验证的 Python 3.11 聚合管线，以来源适配器隔离上游差异，使用 JSON Schema 和最低条目数阻止损坏发布，并通过 GitHub Actions 每日更新 `dist`。

**Tech Stack:** Python 3.11、httpx、BeautifulSoup、markdown-it-py、jsonschema、pytest、GitHub Actions。

## Global Constraints

- 不复制第三方图片，只发布原始 URL。
- 保留作者、来源和原始记录 URL。
- 同步失败不得覆盖上一版有效数据。
- 新来源必须包含解析测试和联网检查。

## Task 1：建立独立仓库身份

- [x] 创建 `hoodax5312-coder/lizuo-prompt-registry` 公开仓库。
- [x] 保留 `yukkcat/image-prompts` 为本地 `upstream` 远端。
- [x] 更新 README、NOTICE、包名和工作流名称。

## Task 2：验证聚合管线

- [ ] 运行 `python3 -m venv .venv`。
- [ ] 运行 `.venv/bin/python -m pip install -e '.[dev]'`。
- [ ] 运行 `.venv/bin/python -m pytest`，预期全部通过。
- [ ] 运行 `.venv/bin/python -m prompt_registry --check`，预期所有来源达到最低条目数且通过 Schema。

## Task 3：发布基线

- [ ] 检查 `git diff --check`。
- [ ] 提交栗作仓库身份与设计文档。
- [ ] 推送 `main` 到 `origin`。
- [ ] 通过 GitHub Raw 读取 `dist/manifest.json` 验证公开发布路径。
