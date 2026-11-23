# 栗作 LIZUO 提示词聚合仓库

[English](README.md) | [提示词记录格式（英文）](docs/prompt-format.md) | [JSON Schema](schema/prompt.schema.json)

集中抓取、解析和校验公开图片提示词来源，并发布统一格式的静态 JSON，供栗作 LIZUO 创作工作台和其他下游应用读取，不必在每个客户端中分别维护来源解析器。

本仓库由栗作独立维护，基础实现来自 MIT 许可的 [yukkcat/image-prompts](https://github.com/yukkcat/image-prompts)。上游仓库继续作为参考实现与更新来源。

- 本地开发根目录为仓库克隆所在的目录。
- `origin/main` 承载下游读取的静态数据，`upstream` 指向参考实现。[GitHub 仓库](https://github.com/hoodax5312-coder/lizuo-prompt-registry)

## 发布数据

同步成功后生成：

- `dist/manifest.json`：格式版本、生成时间、总数、来源元数据、文件路径和 SHA-256。
- `dist/prompts.json`：全部标准化提示词记录。
- `dist/sources/<source-id>.json`：按来源拆分的提示词记录。

消费者应先读取 `dist/manifest.json`，再通过 `promptsPath` 获取完整数据，或通过来源条目的 `path` 获取单个来源。对完整性有要求时，可以使用来源条目的 `sha256` 校验文件。

| 消费端 | 当前默认入口 | 读取方式 |
| --- | --- | --- |
| 栗作客户端 | [GitHub Raw manifest.json][manifest] | 本地网关按 `promptsPath` 读取合并数据。Mac 安装包可先使用随包的 `manifest.json` 和 `prompts.json` 初始化离线缓存。 |
| 栗作在线版 | [GitHub Raw manifest.json][manifest] | 浏览器按 `promptsPath` 读取合并数据，缓存到浏览器数据库。 |
| 栗作管理后台 | 未发现直接消费入口 | 当前代码中未发现对聚合仓或其 manifest 的直接引用。 |

当前合并数据入口见 [GitHub Raw prompts.json](https://raw.githubusercontent.com/hoodax5312-coder/lizuo-prompt-registry/main/dist/prompts.json)。复核某次发布时，将 Raw URL 中的 `main` 替换成同一个完整提交 SHA，再读取清单及其相对路径，避免校验时跨版本。

[manifest]: https://raw.githubusercontent.com/hoodax5312-coder/lizuo-prompt-registry/main/dist/manifest.json

每条记录的字段含义、空值规则、标准化方式、稳定 ID 算法和版本兼容要求见 [Prompt Record Format](docs/prompt-format.md)。机器可读约束见 `schema/prompt.schema.json`。

## 内置来源

- YouMind Seedance 2.0 Prompts
- Banana Prompt Quicker
- Freestylefly GPT Image 2
- Awesome GPT Image
- YouMind GPT Image 2
- YouMind Nano Banana Pro
- Awesome Nano Banana Pro
- PicoTrex Nano Banana Images
- YouMind Gemini 3 Prompts
- YouMind Grok Imagine Prompts
- YouMind Midjourney Syntax Prompts

`youmind-midjourney-syntax` 读取 [YouMind-OpenLab/ai-image-prompts-skill](https://github.com/YouMind-OpenLab/ai-image-prompts-skill) 的清单，抓取其中列出的全部分类文件，只保留使用了 Midjourney 专用参数（如 `--v`、`--niji`、`--sref`、`--stylize`）的提示词；只带 `--ar` 的不算。上游数据没有模型字段，因此这些记录是“按 Midjourney 语法写的提示词”，示例图不保证由 Midjourney 生成。

来源配置位于 [`sources.json`](sources.json)。`id` 是来源和案例 ID 的稳定前缀，`adapter` 选择解析器，`url` 是抓取入口，`homepage` 是展示链接，`minimumItems` 是最低条目数，`model` 是可选的默认模型。调整上游地址时保留既有 `id`，并检查解析结果是否仍对应原来的来源。

## 本地开发

要求 Python 3.11 或更高版本。

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/python -m prompt_registry --check
.venv/bin/python -m prompt_registry
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m prompt_registry --check
.\.venv\Scripts\python -m prompt_registry
```

`--check` 只联网抓取和校验。默认执行会更新 `dist/`，也可以用 `--output /path/to/snapshot` 生成到独立目录。`.venv/`、缓存和其他构建产物均由工具生成。`dist/` 里现有的 Git 跟踪文件是下游读取的发布快照，使用同步命令生成。

## 核对一次更新

1. 记录本地 `HEAD` 和 `git status --short`。用 `git ls-remote origin refs/heads/main` 获取实际远端 SHA，用 `git fetch --no-tags origin <sha>` 取回该快照，避免用过期的本地 `origin/main` 作基线。远端定时任务可并行更新，验收时再确认分支 SHA。
2. 运行测试和同步。抓取失败、解析失败、低于 `minimumItems` 或 schema 校验失败会中止整轮写入，保留上一版有效快照。写入按文件原子替换，最后更新清单。出现失败时记录来源和报错，核对上游地址、格式和条目数后重跑。
3. 用下列命令检查快照和工作区。将 `<sha>` 替换为步骤 1 的实际远端 SHA。

```sh
git diff --check
git diff --stat HEAD -- dist
git diff --stat <sha> -- dist
git show HEAD:dist/manifest.json
git show <sha>:dist/manifest.json
```

4. 对两份基线分别使用 `git show <ref>:dist/sources/<id>.json` 取出逐源旧数据，以案例 `id` 对照新文件。仅新文件有的 ID 计新增，仅旧文件有的 ID 计移除，同 ID 比较完整记录区分修改和无变化。单纯的排序差异单独记录。失败来源标记为无法确认。核对清单的各源 `count`、`sha256`、`total` 与合并数据，并检查工作区里是否只有预期的文档和生成文件变更。

   YouMind 的部分解析器使用上游编号、标题或提示词计算 ID。上游重新编号或修改这些字段时，同一案例可能计作一条新增和一条移除。遇到大批 ID 变化时，再比较去掉 `id` 的记录内容，单独注明内容相同的条数。

## 添加或修改来源

1. 在 `sources.json` 中添加或修改来源配置。
2. 在 `prompt_registry/parsers.py` 中实现或更新解析器。
3. 统一通过 `prompt_registry.models.make_prompt` 生成标准记录。
4. 在 `tests/` 中添加解析样例与断言。
5. 发布前运行完整测试和联网的 `--check`。

不要把来源特有字段直接写进生成记录。只有确实需要新的跨来源字段时，才应有意识地升级公共格式版本。

## 自动更新

工作流计划每天上海时间 11:17 运行，也支持 Actions 手动触发。它使用 Python 3.11，先跑测试，再同步。只有 `dist/` 有变化时才由工作流提交并推送，仅生成时间变化不会产生提交。同步失败时从对应 Actions 日志查看来源和错误。[工作流配置](.github/workflows/sync.yml) · [运行记录](https://github.com/hoodax5312-coder/lizuo-prompt-registry/actions/workflows/sync.yml)

## 版权

同步代码和仓库文档使用 MIT License。提示词、图片、名称和其他上游内容仍受各自原始条款约束。本仓库保留来源标识和地址，不会重新授权上游内容，也只保存图片 URL，不复制图片文件。详见 [NOTICE.md](NOTICE.md)。
