# 灵枢 v1.3

灵枢是一款面向长篇百万字级小说写作的轻量级桌面工作台。它把书籍、分卷、章节、人物卡、世界观、Skills、Truth File、RAG 上下文、长篇生成、长篇审查和全书分析放在同一个本地项目库里，目标是让作者在较长创作周期中持续维护设定、结构和正文一致性。

当前版本窗口标题为 `灵枢v1.3`，正式版产物默认输出为 `灵枢-v1.3.exe`。

---

## 目录

- [当前定位](#当前定位)
- [核心机制](#核心机制)
  - [作品库](#作品库)
  - [右侧抽屉](#右侧抽屉)
  - [AI 用途配置](#ai-用途配置)
  - [智能导入](#智能导入)
  - [长篇生成](#长篇生成)
  - [长篇审查与记录](#长篇审查与记录)
  - [全书分析](#全书分析)
  - [Skills](#skills)
  - [Truth File 与 RAG](#truth-file-与-rag)
  - [导出](#导出)
- [架构概览](#架构概览)
  - [技术栈](#技术栈)
  - [多智能体流水线](#多智能体流水线)
  - [审查引擎与审计维度](#审查引擎与审计维度)
  - [模型路由](#模型路由)
  - [Truth File 体系](#truth-file-体系)
  - [RAG 检索架构](#rag-检索架构)
  - [核心基础设施](#核心基础设施)
- [数据库模型](#数据库模型)
- [本地运行](#本地运行)
- [数据目录](#数据目录)
- [环境变量](#环境变量)
- [打包](#打包)
- [测试](#测试)
- [主要目录](#主要目录)
- [维护原则](#维护原则)

---

## 当前定位

灵枢不是单次文本生成器，而是一个长期维护型小说工程环境：

- 本地 SQLite 保存书籍、卷、章、人物、世界观、Skills、审查记录和快照。
- 正文编辑、大纲编辑、人物卡和世界观使用结构化表单与 Markdown 预览结合。
- AI 能力按用途拆分配置，不同任务可以使用不同模型。
- 长篇生成走多智能体流水线，生成后带一致性审查与修订结果。
- 全书分析走三级金字塔流程，尽量保留原文证据并做证据门禁。
- 智能导入依赖远程模型识别文档类型和章节结构，不再使用本地预设结构猜测。

---

## 核心机制

### 作品库

左侧是作品轨道，结构为：

- 书籍
- 分卷
- 章节
- 模板章节

章节正文、章节大纲、书籍大纲、卷大纲、人物卡和世界观都会写入本地数据库。普通文件导入仍支持本地解析 `.txt`、`.md`、`.docx`。

### 右侧抽屉

右侧抽屉当前包含：

- `概览`：当前书籍概览、书籍上下文预览。
- `快键`：人名快捷插入。
- `生成`：章节/卷相关生成入口。
- `人物`：人物列表与人物卡详情。
- `世界观`：统一世界观模板。
- `Skills`：当前生效 Skills。
- `记录`：长篇生成/审查记录、快照查看与恢复。
- `任务`：后台任务进度、日志和取消按钮。

### AI 用途配置

进入 `设置 -> AI 设置` 配置模型。当前用途包括：

| 用途 | 说明 |
|------|------|
| `写作生成` | 章节草稿生成、续写、润色 |
| `同步大纲` | 根据章节正文自动生成摘要并同步到大纲 |
| `AI概率检测` | 检测正文中 AI 生成痕迹的概率和等级 |
| `AI纠错` | 中文错别字检测与修改建议 |
| `智能导入分类` | 判断导入文档属于正文/大纲/人物/世界观 |
| `Skills提炼` | 从参考文本或开源项目调研资料中提炼可复用写作约束 |
| `全书分析` | 三级金字塔流程，分析全书并回写设定 |
| `长篇生成/校验` | 多智能体流水线生成与审查 |
| `AI 对话` | 多轮对话式写作辅助 |

也可以用环境变量提供默认配置：

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="your-model"
python main.py
```

应用内设置会保存到数据目录下的 `ai_settings.json`。

### 智能导入

`智能导入` 的流程是：

1. 读取 `.txt`、`.md` 或 `.docx`。
2. 使用 `智能导入分类` 用途模型判断文档类型：正文、大纲、人物或世界观。
3. 如果是正文，调用 `ChapterStructureAgent` 识别卷/章标题行，例如 `第一卷`、`第十二章`、`序章`、`番外`。
4. 按智能体返回的 `line_number` 切分正文并创建书籍、分卷和章节。

智能导入需要远程模型。未配置远程模型时无法使用。需要离线导入时，请使用普通导入入口，它仍会使用本地解析规则。

### 长篇生成

`长篇生成` 采用多智能体方案进行流水线处理，根据当前章节大纲生成正文。当前章节已有正文时，系统会在当前章节后创建新章节，避免直接覆盖已有正文。

生成流水线主要包含：

- **Planner（大纲拆解）**：将章节大纲拆解为场景计划，明确每个场景的目标、冲突和转折。
- **Writer（正文写手）**：根据场景计划生成完整章节正文。
- **Auditor（一致性审计）**：审查生成内容的一致性、OOC、AI 痕迹等风险。
- **Reviser（修订润色）**：根据审查意见修订正文。

生成前会保存快照；任务运行状态会显示在 `任务` 抽屉。

流水线支持两种运行模式：

- **单次远程调用**：将全部智能体角色合并到一次 API 请求中，由模型模拟完整流水线。
- **AgentGraph 图编排**：按 Planner → Writer → Auditor → Reviser 顺序逐步调用，每个智能体独立请求，支持模型路由和取消事件。

### 长篇审查与记录

审查结果会进入 `记录` 抽屉。记录支持：

- 查看单次运行详情。
- 查看 Truth File 快照。
- 恢复审查快照。
- 复制审查使用的 Truth File。

审查流程同样支持两种模式：

- **单次远程审查**：一次 API 调用完成审查与修订。
- **AgentGraph 审查**：Auditor → Reviser 逐步调用。

此外，灵枢还支持**跨章节一致性检查**，检查维度包括人物状态（character）、世界观设定（world）和剧情事实（fact），帮助发现跨章节矛盾。

### 全书分析

全书分析使用三级流程：

1. **一级（源文本解读）**：按约 20000 字原文片段做忠实精简解读，提取关键事件、人物线索、世界观线索，并输出带 `evidence_quote` 的 `source_facts`。
2. **二级（结构整合）**：压缩并整合一级结果，构建因果链条、时间线、人物弧光和世界观模型，保留证据引用链。
3. **三级（模板写回）**：生成书籍大纲、世界观、人物卡和章节事件更新，并根据需要请求原文回查。分两步执行：
   - **草案**：产出可写回草案，同时审查证据是否足够，对存疑字段输出 `source_requests`。
   - **原文复核**：根据草案中的回查请求，从本地原文中检索相关片段，对草案进行证据门禁和精填。

写回时会做证据门禁：证据不足的字段会被丢弃或进入待确认提示，避免无证据覆盖正式设定。

### Skills

Skills 是可复用写作约束，支持全局、书籍、章节三级绑定。可从参考文本或项目调研资料中提炼 Skills，再绑定到当前创作上下文。

每个 Skill 包含以下字段：

| 字段 | 说明 |
|------|------|
| `name` | Skill 名称 |
| `category` | 分类（如叙事、对白、节奏等） |
| `summary` | 简要描述 |
| `instruction` | 具体写作约束指令 |
| `use_cases` | 适用场景 |
| `risk_note` | 使用风险提示 |

Skills 提炼来源：

- **参考文本提炼**：从导入的参考书籍中提炼抽象写作技法。
- **项目调研提炼**：从 GitHub/开源 AI 写作项目调研资料中提炼产品策略和工作流，自动标注 license 和可复用级别。

生成、审查和对话会读取当前生效 Skills 作为约束。

### Truth File 与 RAG

灵枢会在数据目录内维护 Truth File，用于汇总书籍设定、章节摘要、伏笔和审查上下文。RAG 向量库默认使用本地数据目录下的 `rag_vectors`，内置 fallback embedding；安装可选依赖后可启用更完整的向量检索与重排序。

### 导出

灵枢支持多种导出格式和粒度：

| 导出类型 | 格式 | 说明 |
|----------|------|------|
| 全书导出 | TXT / Markdown / DOCX | 包含大纲、人物卡、世界观和全部章节正文 |
| 章节导出 | TXT / Markdown / DOCX | 单章节内容 |
| 纯正文 | TXT | 仅导出全部章节正文，不含大纲和设定 |
| 纯大纲 | TXT | 仅导出章节大纲 |
| 纯人物卡 | TXT | 仅导出人物卡 |
| 纯世界观 | TXT | 仅导出世界观设定 |
| 按卷导出 | TXT | 每卷一个独立文件 |

导出文件默认保存到数据目录下的 `exports/`。

---

## 架构概览

### 技术栈

| 层面 | 技术 |
|------|------|
| GUI 框架 | PyQt6 |
| 数据库 | SQLite（本地 `novels.db`） |
| AI 服务 | OpenAI 兼容 API（多用途模型路由） |
| 向量检索 | Qdrant（本地嵌入式）+ Jina Reranker |
| 文档处理 | python-docx |
| 打包 | PyInstaller + C# Launcher |
| 测试 | pytest |
| Python | 3.13+ |

### 多智能体流水线

灵枢的核心生成与审查能力基于 `AgentGraph` 实现，采用纯 Python 的图编排方案：

```
生成流水线：                          审查流水线：

Planner(大纲拆解)                    Auditor(长篇审查)
       ↓                                   ↓
Writer(正文写手)                     Reviser(修订润色)
       ↓
Auditor(一致性审计)
       ↓
Reviser(修订润色)
```

每个智能体通过 `AgentState` 数据类传递状态，包含：

- 输入：`book_title`、`chapter_title`、`outline`、`current_content`、`truth_file`、`selected_skills` 等
- 中间产物：`plan`（场景计划）、`draft`（草稿）、`audit_findings`（审查发现）
- 输出：`revised_content`（修订正文）、`revised_outline`（修订大纲）、`overall_score`、`final_verdict`

流水线支持**取消事件**（`cancel_event`），可在任意节点中断执行。

### 审查引擎与审计维度

审查引擎（`AuditEngine`）内置 26 条审计规则，覆盖 12 个维度：

| 维度 ID | 维度名称 | 权重 | 规则数 |
|---------|---------|------|--------|
| `plot_structure` | 情节结构 | 1.2 | 3 |
| `character_continuity` | 人物连续性 | 1.5 | 3 |
| `world_consistency` | 世界观一致性 | 1.3 | 3 |
| `logic_coherence` | 逻辑连贯性 | 1.2 | 3 |
| `style_stability` | 风格稳定性 | 0.8 | 2 |
| `ooc_detection` | OOC 检测 | 1.5 | 2 |
| `ai_flavor` | AI 痕迹检测 | 1.0 | 3 |
| `hook_tracking` | 伏笔追踪 | 0.9 | 2 |
| `emotion_arc` | 情感弧光 | 0.7 | 1 |
| `dialogue_quality` | 对话质量 | 0.8 | 2 |
| `pacing` | 节奏控制 | 0.8 | 1 |
| `template_alignment` | 模板对齐 | 0.6 | 1 |

评分算法：基础分 100，按问题严重程度（high/medium/low）和维度权重计算扣分，最终得分 0-100。

判决规则：
- `approve`：无 high 问题且得分 ≥ 80
- `revise`：1 个 high 问题
- `reject`：≥ 2 个 high 问题或得分 < 60

### 模型路由

`ModelRouter` 支持为不同智能体分配不同模型和参数，内置三种预设：

| 预设 | 说明 |
|------|------|
| `default` | 所有 Agent 使用统一模型 |
| `budget` | 经济配置，审查类 Agent 使用廉价模型节省成本 |
| `quality` | 质量优先，写作和审计使用推理模型，大纲和修订使用普通模型 |

每个智能体的默认参数：

| 智能体 | 默认 temperature | 默认 max_tokens |
|--------|-----------------|----------------|
| Planner(大纲拆解) | 0.3 | 4096 |
| Writer(正文写手) | 0.7 | 8192 |
| Auditor(一致性审计) | 0.25 | 4096 |
| Auditor(长篇审查) | 0.25 | 4096 |
| Reviser(修订润色) | 0.4 | 8192 |

支持通过 `set_override()` 对单个智能体进行自定义覆盖。

### Truth File 体系

Truth File 是灵枢维护全书一致性状态的核心机制，由 `TruthManager` 管理，存储在数据目录下的 `{book_id}/` 子目录中。

包含 7 个文件：

| 文件名 | 标签 | 说明 |
|--------|------|------|
| `current_state.md` | 当前状态 | 全书大纲、人物总览、世界观设定、章节进度 |
| `character_matrix.md` | 人物矩阵 | 人物关系列表 |
| `pending_hooks.md` | 待回收伏笔 | JSON 格式的伏笔记录，支持注册和回收 |
| `chapter_summaries.md` | 章节摘要 | 每章大纲和摘要 |
| `subplot_board.md` | 支线看板 | 自动提取的支线线索 |
| `emotional_arcs.md` | 情感弧光 | 角色情感状态追踪 |
| `particle_ledger.md` | 关键道具 | 道具/物品账本 |

`assemble_context()` 方法按优先级拼接 Truth File 内容，为生成和审查提供上下文，默认上限 14000 字符。单个 Truth File 上限 18000 字节。

### RAG 检索架构

`ChapterRetriever` 提供混合检索能力：

- **向量检索**：使用 Qdrant 本地嵌入式模式，支持 API Embedder 和内置 FallbackEmbedder。
- **BM25 检索**：内置 BM25 算法，支持中文分词，索引持久化到 `bm25.json`。
- **混合排序**：使用 RRF（Reciprocal Rank Fusion）合并向量检索和 BM25 检索结果。
- **重排序**：可选 Jina Reranker 对混合结果进行精排。
- **时间衰减**：`search_with_recency()` 支持按章节新近度加权，优先返回近期章节。

索引内容：
- 章节级：标题 + 大纲 + 摘要
- 书籍级：书籍大纲和世界观设定

### 核心基础设施

| 模块 | 说明 |
|------|------|
| `EventBus` | 发布-订阅事件总线，减少组件间直接依赖 |
| `ServiceLocator` | 服务定位器，统一管理全局服务实例 |
| `AppState` | 全局应用状态管理 |

---

## 数据库模型

灵枢使用 SQLite 存储所有数据，主要表结构如下：

| 表名 | 说明 |
|------|------|
| `books` | 书籍：标题、大纲（text + JSON）、世界观（text + JSON）、封面 |
| `volumes` | 分卷：所属书籍、标题、大纲、排序 |
| `chapters` | 章节：所属书籍/分卷、标题、大纲、正文、摘要、AI概率、排序 |
| `characters` | 人物：所属书籍、姓名、角色、人物卡（text + JSON）、头像、位置 |
| `character_relationships` | 人物关系：关系类型、描述 |
| `world_entries` | 世界观条目：名称、分类、内容 |
| `chapter_snapshots` | 章节快照：生成/审查前的正文备份 |
| `chapter_events` | 章节事件：关键事件标签和描述 |
| `chapter_tags` | 章节标签：如 `template` 标记模板章节 |
| `chapter_ai_spans` | AI 生成区间：记录正文中 AI 生成的文本范围 |
| `review_runs` | 审查运行记录：评分、判决、修订正文、Truth File 快照 |
| `review_findings` | 审查发现：智能体、严重度、类别、引用、问题和建议 |
| `reference_sources` | 参考资料来源：标题、作者、license、可复用级别 |
| `distilled_skills` | 提炼的 Skills：名称、分类、指令、风险提示 |
| `skill_bindings` | Skills 绑定：全局/书籍/章节三级绑定 |
| `name_shortcuts` | 人名快捷键 |
| `node_styles` | 星图节点样式（兼容保留） |
| `relationship_types` | 星图关系类型（兼容保留） |
| `sticky_notes` | 便签 |
| `legacy_imports` | 旧版数据导入记录，防止重复导入 |

数据库支持自动迁移：新增列通过 `_ensure_column()` 安全添加，结构化模板迁移通过 `app_migrations` 表追踪。

---

## 本地运行

建议使用 Python 3.13 或当前项目已验证的 Python 环境。

```powershell
python -m pip install -r requirements.txt
python main.py
```

如果只想验证启动流程，可设置：

```powershell
$env:SIMPLE_AI_NOVEL_SMOKE_EXIT="1"
python main.py
```

启动流程：

1. 显示启动画面（`StartupSplash`）
2. 初始化数据库（`Database`）
3. 加载 AI 配置（`SimpleAIService.from_env()`）
4. 构建主窗口（`run_qt_app()`）

---

## 数据目录

源码运行时默认使用项目根目录下的 `data/`。打包后的 exe 会把用户数据放在 exe 同级的 `data/`。

可通过环境变量覆盖数据目录：

```powershell
$env:SIMPLE_AI_NOVEL_DATA_DIR="D:\LingShuData"
python main.py
```

数据目录中常见文件/目录：

| 路径 | 说明 |
|------|------|
| `novels.db` | 主数据库 |
| `ai_settings.json` | AI 用途配置 |
| `ui_settings.json` | 界面配置 |
| `references/imported_books/` | 导入的参考书籍 |
| `references/github_projects/` | GitHub 项目调研资料 |
| `media/book_covers/` | 书籍封面 |
| `media/character_images/` | 人物头像 |
| `exports/` | 导出文件 |
| `rag_vectors/` | 本地向量索引 |
| `{book_id}/` | 每本书的 Truth File 目录 |

---

## 环境变量

| 变量名 | 说明 |
|--------|------|
| `OPENAI_API_KEY` | AI 服务 API Key |
| `OPENAI_BASE_URL` | AI 服务 Base URL（默认 `https://api.openai.com/v1`） |
| `OPENAI_MODEL` | 默认模型名称 |
| `SIMPLE_AI_NOVEL_DATA_DIR` | 数据目录路径 |
| `SIMPLE_AI_NOVEL_SMOKE_EXIT` | 设为 `1` 时仅验证启动流程后退出 |
| `SIMPLE_AI_NOVEL_QT_OFFSCREEN` | 设为 `1` 时跳过启动画面 |
| `SIMPLE_AI_NOVEL_NATIVE_SPLASH` | 设为 `1` 时使用原生启动画面 |
| `SIMPLE_AI_NOVEL_LEGACY_DATA_DIRS` | 旧版数据目录路径（多个用 `;` 分隔） |

---

## 打包

正式版打包脚本位于 `packaging/build_first_exe_fast.ps1`，产物格式为：

```text
release/{ProductName}-{Version}.exe
```

v1.3 正式版示例：

```powershell
powershell -ExecutionPolicy Bypass -File "packaging\build_first_exe_fast.ps1" `
  -Version "v1.3" `
  -ProductName "灵枢" `
  -ReuseRuntimeFrom "v1.3预览版-aac33b27"
```

打包会复制应用代码、嵌入启动图和图标、复用或创建 Python runtime 缓存、压缩 payload，并编译 C# 启动器。

Windows PowerShell 5.1 对中文路径和 UTF-8 BOM 比较敏感；如果遇到 `param` 解析错误或产物中文名乱码，先检查脚本是否为 UTF-8 with BOM。详细规则见 `packaging/BUILD_RULES.txt`。

---

## 测试

常用回归命令：

```powershell
python -m pytest test_qt_helpers.py
python -m pytest tests/test_agents.py tests/test_text_importer.py
python -m pytest test_database_extensions.py tests/test_star_graph_models.py tests/test_star_graph_history.py tests/test_star_graph_style_manager.py
python -m compileall novel_app
```

完整测试：

```powershell
python -m pytest
```

测试文件分布：

| 文件 | 覆盖范围 |
|------|---------|
| `tests/test_agents.py` | 多智能体流水线 |
| `tests/test_audit.py` | 审查引擎与审计维度 |
| `tests/test_text_importer.py` | 文本导入 |
| `tests/test_rag_modules.py` | RAG 向量检索 |
| `tests/test_truth_manager.py` | Truth File 管理 |
| `tests/test_star_graph_models.py` | 星图数据模型 |
| `tests/test_star_graph_history.py` | 星图历史记录 |
| `tests/test_star_graph_style_manager.py` | 星图样式管理 |
| `test_qt_helpers.py` | Qt 行为和源码结构回归 |
| `test_core_modules.py` | 核心模块 |
| `test_database_extensions.py` | 数据库扩展 |

---

## 主要目录

```text
main.py                         应用启动入口
novel_app/
├── qt_app.py                   主窗口、业务协调和兼容入口
├── ai_service.py               AI 服务、用途调用和远程请求
├── model_router.py             模型路由（预设/自定义/按智能体分配）
├── database.py                 SQLite 数据模型与迁移
├── text_importer.py            普通导入与智能体结构切分支持
├── exporter.py                 多格式导出（TXT/Markdown/DOCX）
├── prompt_settings.py          提示词配置
├── prompt_utils.py             提示词工具函数
├── secure_storage.py           安全存储
├── structured_templates.py     结构化模板（书籍大纲/人物卡/世界观）
├── research_sources.py         项目调研资料管理
├── agents/                     多智能体生成、审查和章节结构识别
│   ├── graph.py                AgentGraph 图编排与 AgentState
│   ├── planner.py              Planner 智能体（大纲拆解）
│   ├── writer.py               Writer 智能体（正文写手）
│   ├── auditor.py              Auditor 智能体（一致性审计）
│   ├── reviser.py              Reviser 智能体（修订润色）
│   ├── chapter_structure.py    ChapterStructureAgent（章节结构识别）
│   └── prompts.py              智能体提示词
├── audit/                      审查系统
│   ├── rules.py                审计规则与评分引擎
│   ├── dimensions.py           12 个审计维度定义
│   ├── dsl_parser.py           DSL 解析器
│   └── validator.py            验证器
├── core/                       核心基础设施
│   ├── event_bus.py            发布-订阅事件总线
│   ├── service_locator.py      服务定位器
│   └── state.py                全局状态
├── qt/                         Qt UI 层
│   ├── drawer/                 右侧抽屉页面
│   │   ├── overview.py         概览
│   │   ├── shortcuts.py        快键（人名快捷插入）
│   │   ├── skills.py           Skills 管理
│   │   ├── characters.py       人物卡
│   │   ├── world.py            世界观
│   │   ├── review.py           审查记录
│   │   ├── tasks.py            后台任务
│   │   ├── outline.py          大纲
│   │   └── controller.py       抽屉控制器
│   ├── forms.py                书籍大纲、人物卡、世界观结构化表单
│   ├── dialogs.py              通用对话框
│   ├── character_dialog.py     人物编辑对话框
│   ├── chat_dialog.py          AI 对话窗口
│   ├── correction_dialog.py    纠错对话框
│   ├── star_graph*.py          星图 UI（已下线，保留兼容）
│   ├── startup.py              启动画面
│   ├── theme.py                主题
│   ├── workers.py              后台工作线程
│   ├── helpers.py              UI 辅助函数
│   ├── icons.py                图标
│   ├── image_utils.py          图片工具
│   └── state.py                UI 状态
├── rag/                        RAG 向量检索
│   ├── embedder.py             嵌入（APIEmbedder + FallbackEmbedder）
│   ├── qdrant_client.py        Qdrant 本地客户端
│   ├── reranker.py             Jina Reranker
│   └── retriever.py            混合检索器（向量 + BM25 + RRF）
├── truth/                      Truth File 管理
│   └── truth_manager.py        7 个 Truth File 的构建与组装
├── theme/                      主题系统
│   ├── colors.py               颜色定义
│   ├── typography.py           字体排版
│   ├── spacing.py              间距规范
│   ├── design_tokens.py        设计令牌
│   └── theme_customization.py  主题自定义
└── state/                      应用状态
    └── app_state.py            全局应用状态
packaging/                      Windows exe 打包脚本和启动器
tests/                          模块级测试
```

---

## 维护原则

- `novel_app.qt_app` 仍保留公共导入兼容入口。
- 新 UI 页面优先拆到 `novel_app/qt/drawer/` 或 `novel_app/qt/` 子模块。
- 不在主窗口继续堆积页面构建代码。
- 涉及远程 AI 的功能应明确用途配置和失败路径。
- 智能导入正文切分以章节结构智能体结果为准，不恢复本地预设结构兜底。
- 星图 UI 已下线；底层星图数据/样式相关代码暂时保留，以兼容现有数据和测试。
