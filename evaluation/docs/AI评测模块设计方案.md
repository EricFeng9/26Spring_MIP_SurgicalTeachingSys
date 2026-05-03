# AI 评测模块设计方案

## 1. 模块定位

AI 评测模块属于教学复盘层，目标不是重新评分，而是把 `evaluator.py` 已经算出的客观评分结果，转化为学员能直接理解和执行的教学反馈。

核心边界如下：

- `evaluator.py`：负责确定分数、扣分项、关键指标，是唯一计分来源。
- `ai_processor.py`：负责接收评分结果、病例信息、评分细则、RAG 临床知识，并调用大模型生成教学反馈报告。
- RAG 知识库：只补充临床机制、风险解释和训练建议，不参与分数计算。
- LLM：只负责组织语言和结构化输出，不允许改分、不允许补造扣分项。
- `evaluation/main/src`：只提供可复用功能模块，不配置任何路径、模型、API Key、测试样本或业务流程。
- `evaluation/test/src`：只负责全链路模拟和调用样例，展示上层模块如何把路径、输入数据和配置传给 `main/src`。

因此，本模块的第一性问题是：**如何让学员知道自己为什么扣分、临床风险是什么、下一次具体怎么改。**

## 0. 当前实现状态（2026-05-02）

当前代码已经进入“本地评分 + RAG 构建 + AI 教学反馈调用”联调阶段。

已经完成：

- `evaluation/main/src/main.py`：统一入口 `evaluate_with_ai_feedback(...)`，上层只需调用该入口即可完成本地评分和 AI 教学反馈调用。
- `evaluation/main/src/ai_processor.py`：已实现 OpenAI-compatible embedding、ChromaDB 检索、OpenAI-compatible chat 调用和三字段 JSON 校验。
- `evaluation/main/src/rag_builder.py`：已实现 PDF 扫描、PDF 按页解析、规则分块、embedding、ChromaDB 入库、manifest 增量更新。
- `evaluation/test/src/build_rag.py`：已实现测试层 RAG 构建入口和自检查。
- `evaluation/test/src/test_evaluator.py`：已改为调用 `main.py`，测试层负责准备路径和配置。
- `evaluation/test/src/config.json`：已集中配置测试样本、RAG 路径、LLM 和 embedding 参数。
- `evaluation/test/rag/raw_docs/`：已放入公开来源的眼底激光、视网膜裂孔、糖网激光 PDF 资料。

当前测试样本：

```text
evaluation/test/sample_data/2604_sampledata/4226701
```

当前输出目录：

```text
evaluation/test/output/4226701
```

当前模型配置：

- Chat model：`deepseek-v4-flash`
- Embedding model：`text-embedding-3-small`
- Base URL：由测试配置 `evaluation/test/src/config.json` 提供

仍需后续优化：

- `rag_builder.py` 当前使用规则切块，尚未调用 LLM 做知识块语义重写和标签增强。
- `ai_processor.py` 当前只返回 `advantage`、`disadvantage`、`improvement`，不返回 RAG 引用给前端。
- RAG 命中质量还需要结合真实医生资料继续调 chunk 粒度、query 生成和标签策略。

不解决的问题：

- 不重新计算覆盖范围、激光参数空间适配度、点位均匀性。
- 不替代 `evaluator.py` 的规则评分。
- 不让大模型根据主观判断调整分数。
- 不在第一阶段引入专家案例库。

## 2. 分层原则

本项目必须严格区分“功能模块”和“调用接入层”。

### 2.1 `main/src` 的职责

`evaluation/main/src` 只实现模块能力：

- RAG 资料库构建能力。
- PDF 文本解析、分块、知识块结构化。
- ChromaDB 写入、删除、检索能力。
- 评分结果事实提取能力。
- LLM 输入组装能力。
- LLM 输出 JSON 校验能力。
- 教学反馈 JSON 生成能力。

`main/src` 可以接收路径参数并读写对应文件，但路径必须由调用方传入。`main/src` 不允许自己决定默认目录。

### 2.2 `main/src` 禁止事项

`main/src` 不允许做以下事情：

- 不写死 `evaluation/rag/raw_docs/`、`evaluation/test/output/` 等项目路径。
- 不读取固定测试样本。
- 不直接读取环境变量。
- 不内置 `AI_BASE_URL`、`AI_API_KEY`、模型名或 embedding 模型名。
- 不判断当前是“游戏启动”“测试启动”还是“后端调用”。
- 不在内部决定是否需要首次构建或增量更新；只根据调用方传入的参数执行。
- 不把 `test/src` 当作生产依赖。
- 不静默吞掉配置缺失、模型失败、PDF 解析失败或非法 JSON。

### 2.3 上层调用方的职责

上层调用方可以是：

- `evaluation/test/src` 中的测试脚本。
- 游戏后端服务。
- 桌面调试脚本。
- 后续正式部署服务。

上层调用方负责：

- 决定资料目录在哪里。
- 决定 ChromaDB 存储在哪里。
- 决定 manifest/cache/output 路径。
- 读取评分 JSON、评分细则、病例 JSON、prompt 文件。
- 读取环境变量或配置文件。
- 构造 `llm_config` 和 `embedding_config`。
- 决定何时调用 RAG 构建模块。
- 决定何时调用教学反馈生成模块。
- 保存最终报告文件。

### 2.4 `test/src` 的定位

`evaluation/test/src` 是全链路模拟层，不是核心模块层。

它应该展示：

- 如何调用 `evaluator.py` 生成评分结果。
- 如何准备 RAG 构建目录和模型配置。
- 如何调用 `rag_builder.py` 构建或更新向量库。
- 如何读取测试输入文件。
- 如何调用 `ai_processor.py` 生成教学反馈 JSON。
- 如何把结果写入 `evaluation/test/output/`。

因此，`test/src` 可以写死测试样本路径；`main/src` 不可以。

## 3. 技术选型

### 3.1 不使用 LangChain

当前链路是固定流程：

评分 JSON -> 生成检索 query -> ChromaDB 检索 -> 拼接 prompt -> 调用 LLM -> 校验 JSON。

这不是复杂 Agent 任务，也不需要工具调用、动态规划、多轮链式推理或复杂编排。使用 LangChain 会带来额外抽象层，使调试 prompt、追踪输入输出和定位 JSON 格式错误更困难。

因此不使用 LangChain，直接用：

- `chromadb` 管理本地向量库。
- OpenAI-compatible HTTP/API Client 调用 embedding 和 chat model。
- Python 原生函数组织流程。

这样链路更短，行为更透明，也更符合课程项目展示需求。

### 3.2 RAG 使用 ChromaDB

RAG 知识库采用本地持久化 ChromaDB，并通过资料目录自动构建。使用者只需要把医生提供的 PDF 电子书、PDF 格式课件放入上层指定的资料目录，调用方在首次启动或资料更新时调用 RAG 构建模块，模块自动解析、分块、生成向量并写入 ChromaDB。

选择原因：

- 支持本地持久化，方便随项目目录一起演示。
- 能保存文本、向量、metadata，适合临床知识分块检索。
- 不依赖外部数据库服务，部署成本低。
- 比手写关键词检索更接近真实 RAG 架构。
- 支持增量更新：新增、修改、删除资料后，只重建受影响文件对应的知识块。

测试层建议目录如下，仅作为 `test/src` 调用样例，不是 `main/src` 默认路径：

```text
evaluation/
  test/
    rag/
      raw_docs/
        textbook_retinal_laser.pdf
        lecture_retinal_tear.pdf
      parsed_cache/
      chunk_cache/
      chroma_db/
      rag_manifest.json
```

目录职责：

- `raw_docs/`：原始资料目录，只放医生资料 PDF 或 PDF 课件。
- `parsed_cache/`：PDF 解析后的按页文本缓存。
- `chunk_cache/`：大模型或规则分块后的结构化知识块缓存。
- `chroma_db/`：ChromaDB 持久化目录。
- `rag_manifest.json`：记录每个源文件的 hash、索引状态、chunk 数量和更新时间。

PDF 解析优先选择 `PyMuPDF`；如果后续资料版面复杂、表格和双栏较多，再升级为 `Docling`。核心原则是：解析器负责保留页码和原文，大模型负责理解和结构化，程序负责校验和入库。

### 3.3 LLM 使用 OpenAI-compatible 接口

`ai_processor.py` 不绑定具体厂商 SDK，而是使用 OpenAI-compatible 接口。模型连接信息必须由上层调用方传入，`main/src` 不直接读取环境变量。

上层调用方可以从环境变量、配置文件或后端配置中心读取：

```text
AI_BASE_URL
AI_API_KEY
AI_CHAT_MODEL
AI_EMBEDDING_MODEL
```

然后组装为显式配置对象传给 `main/src`。这样可以接入 OpenAI、DeepSeek、通义兼容接口或学校部署的兼容网关。后续切换模型时，不需要改核心模块代码。

## 4. 整体流程

整体分成两个流程：资料库构建流程和教学反馈生成流程。

### 4.1 资料库自动构建流程

```text
上层调用方决定需要构建或更新资料库
  |
  | 1. 调用 build_or_update_rag_database(...)
  v
扫描 raw_docs_dir 并计算文件 hash
  |
  | 2. 对比 rag_manifest.json
  v
判断新增 / 修改 / 删除 / 未变化
  |
  | 3. 只处理新增和修改文件
  v
PDF 解析为按页文本
  |
  | 4. LLM 或规则生成结构化知识块
  v
chunk JSON 校验
  |
  | 5. embedding
  v
写入 ChromaDB
  |
  | 6. 更新 rag_manifest.json
  v
RAG 数据库可检索
```

调用方可以在首次启动、资料更新按钮、后台管理接口或测试脚本中触发该流程。`main/src` 不判断“启动时机”，只根据传入的目录和 manifest 状态执行全量构建或增量更新。

如果 `chroma_db_path` 不存在或 `manifest_path` 不存在，则全量构建。资料更新时，只重建变更文件对应的 chunk。未变化文件必须跳过，避免每次调用都重新解析和重新 embedding。

### 4.2 教学反馈生成流程

```text
上层调用方
  |
  | 1. 调用 evaluator.evaluate() 或读取已有评分结果
  v
玩家最终得分 JSON
  |
  | 2. 读取评分细则、病例文本、引导提示词、模型配置
  v
ai_processor.py
  |
  | 3. 从评分结果中提取最低分项、扣分项、诊断信息
  v
检索 query
  |
  | 4. 到 ChromaDB 检索临床教学知识
  v
RAG 片段
  |
  | 5. 拼接 LLM 输入
  v
大语言模型
  |
  | 6. 返回结构化教学反馈 JSON
  v
前端展示 / 后端存档
```

输入优先级必须固定：

1. 玩家最终得分 JSON：最高优先级，所有分数和扣分事实以它为准。
2. 病例文本信息 JSON：提供疾病、检查结果和诊断上下文。
3. 评分细则 Markdown：用于解释分数含义。
4. RAG 临床知识：用于补充医学机制、风险和改进建议。
5. 引导提示词：约束输出格式、语气和禁用内容。

## 5. RAG 知识库设计

### 5.1 RAG 的职责

RAG 只回答三个问题：

1. 当前病例是什么临床问题？
2. 当前扣分项在临床上为什么重要？
3. 下次训练应该怎么改，观察什么指标？

RAG 不回答：

- 玩家应该得多少分。
- 当前评分算法是否合理。
- 是否应该改变扣分。
- 未出现在评分 JSON 里的错误。

### 5.2 知识来源

第一阶段不手写知识库，也不逐条人工编码知识。知识来源是调用方传入的 `raw_docs_dir` 下的医生资料：

- PDF 电子书。
- PDF 格式演示文稿。
- 后续可扩展到 Markdown、Word、网页导出 PDF，但第一阶段只承诺 PDF。

资料导入后，系统自动抽取临床教学知识。大模型可以参与“理解型工作”，但不直接管理数据库。

大模型负责：

- 判断资料内容对应的疾病、操作原则和风险点。
- 将长段教材或课件内容整理为短知识块。
- 生成 `title`、`disease_tags`、`score_tags`、`keywords`、`summary`。
- 提取与知识块最相关的原文短摘录。

程序负责：

- 扫描文件、计算 hash、判断增量更新。
- 解析 PDF 页码和原文。
- 生成稳定 `chunk_id`。
- 校验 LLM 输出 JSON。
- 调 embedding。
- 写入或删除 ChromaDB 中对应 chunk。
- 更新 `rag_manifest.json`。

### 5.3 自动抽取的知识范围

自动抽取时优先保留与教学反馈直接相关的知识：

| 知识类别 | 作用 | 对应评分问题 |
| :--- | :--- | :--- |
| 视网膜裂孔光凝治疗目标 | 解释为什么要围绕裂孔形成有效封锁 | 覆盖范围不足 |
| 裂孔周围包绕式光凝原则 | 解释连续封锁带、漏打、边界控制 | 覆盖范围不足、越界 |
| 黄斑、视盘、大血管危险区 | 解释红线和安全边界 | 医疗事故、血管扣分 |
| 激光参数空间适配度 | 解释 GT 参数空间策略、玩家参数场和局部参数偏差 | 功率/光斑直径/曝光时间/波长空间偏差 |
| 功率、曝光时间、光斑直径与组织反应 | 解释局部能量过强、过弱、作用范围不匹配的后果 | 参数空间偏差 |
| 波长选择与组织吸收特性 | 解释局部非推荐波长的临床含义 | 波长空间偏差 |
| 光斑间距、重叠与局部热量堆积 | 解释扎堆、重叠、间距不稳风险 | 点位均匀性、重叠扣分 |

低优先级内容不进入第一阶段索引：

- 与眼底光凝教学反馈无关的流行病学背景。
- 目录、参考文献、版权页、课程口号。
- 无法追溯页码的内容。
- 没有明确临床教学意义的泛泛介绍。

### 5.4 知识块结构

每个知识块是一个可独立检索、可直接放入 prompt 的最小教学单元。

推荐字段：

```json
{
  "chunk_id": "sha256_xxx_p12_c03",
  "source_file": "lecture_retinal_tear.pdf",
  "source_type": "pdf_slide",
  "page_start": 12,
  "page_end": 13,
  "title": "视网膜裂孔周围需要形成连续光凝封锁带",
  "disease_tags": ["retinal_tear", "视网膜裂孔"],
  "score_tags": ["position_coverage", "spatial_parameter_adaptation", "missed_area"],
  "keywords": ["裂孔", "包绕式光凝", "封锁带", "漏打", "参数空间适配", "视网膜脱离"],
  "source_quote": "原文中与该知识块最相关的一小段摘录",
  "summary": "裂孔周围光凝需要形成连续封锁带，覆盖不足会增加封闭失败和视网膜脱离风险。",
  "text": "视网膜裂孔光凝的关键目标是在裂孔周围形成连续、完整的粘连屏障，减少玻璃体牵拉导致液化玻璃体进入视网膜下的风险。若封锁带不连续或覆盖不足，可能无法有效阻断裂孔进展，增加视网膜脱离风险。"
}
```

字段说明：

- `chunk_id`：稳定唯一标识，用于引用和调试。
- `source_file`：来源文件名。
- `source_type`：资料类型，例如 `pdf_textbook` 或 `pdf_slide`。
- `page_start` / `page_end`：来源页码，必须保留。
- `title`：知识块标题，方便查看 RAG 命中结果。
- `disease_tags`：疾病标签，用于按病例诊断过滤。
- `score_tags`：评分问题标签，用于按扣分项过滤。
- `keywords`：辅助检索词。
- `source_quote`：原文短摘录，用于追溯，不直接展示给学员。
- `summary`：面向检索的短摘要。
- `text`：进入 LLM 的正文。

必须保留 `source_file` 和页码。否则无法判断反馈依据是否真的来自医生资料。

### 5.5 增量更新策略

`rag_manifest.json` 用于记录资料库状态。

示例结构：

```json
{
  "version": 1,
  "embedding_model": "text-embedding-xxx",
  "files": {
    "lecture_retinal_tear.pdf": {
      "sha256": "abc123",
      "indexed_at": "2026-04-29T10:30:00",
      "chunk_count": 24,
      "status": "indexed"
    }
  }
}
```

更新规则：

- 新增文件：解析、分块、embedding、入库。
- 修改文件：删除旧 `source_file` 对应 chunk，再重新入库。
- 删除文件：删除 ChromaDB 中该 `source_file` 对应 chunk，并更新 manifest。
- 未变化文件：跳过。

### 5.6 检索策略

`ai_processor.py` 从评分结果中生成 query。

以当前样本为例：

```json
{
  "diagnosis": "视网膜裂孔",
  "lowest_score_item": "激光参数空间适配度 24.03/35",
  "penalties": "光斑重叠 4 次",
  "query": "视网膜裂孔 激光参数空间适配度 曝光时间偏差 波长偏差 上方左侧 参数热力图 光斑重叠 局部热量堆积"
}
```

检索规则：

- 默认 `top_k = 5`。
- 优先召回与诊断匹配的知识块。
- 优先召回与最低得分项匹配的知识块。
- 若存在扣分项，再召回对应扣分知识块。
- 不把整份评分细则放入 RAG；评分细则作为独立输入。

重叠扣分定义：

- `evaluator.py` 只把明显重叠写入评分 JSON。
- 对两个光斑，设中心距为 `d`，半径为 `r1/r2`。
- 重叠深度为 `h = r1 + r2 - d`。
- 当 `h / min(r1, r2) >= 0.15` 时，计为一次有效重叠。
- AI 反馈只能引用评分 JSON 中已经计算出的重叠次数，不重新判断图片中的重叠。

### 5.7 当前样本应命中的知识

当前 `Temp770298_sample_v4/score_result.json` 的关键事实：

- 总分：`85.03/100`
- 覆盖范围：`35/35`
- 激光参数空间适配度：`24.03/35`
- 曝光时间：`4.79/8`，平均误差 `0.4018`，主要偏差区域为 `上方左侧曝光时间偏差较高`
- 波长：`5.19/8`，平均误差 `0.3516`，主要偏差区域为 `上方左侧波长偏差较高`
- 点位均匀性：`30/30`
- 光斑重叠：`4` 次
- 病例诊断：`视网膜裂孔`

RAG 至少应命中：

- 激光参数需要与不同治疗区域的专家空间策略匹配。
- 曝光时间偏长或局部能量偏强会增加热损伤风险。
- 波长选择应符合组织吸收和治疗目标，局部非推荐波长会影响治疗机制。
- 有效光斑重叠会造成局部热量堆积，增加组织损伤风险。

## 6. 接口设计

### 6.1 配置对象规范

`main/src` 不读取环境变量，所有模型配置必须由调用方显式传入。

LLM 配置：

```python
llm_config = {
    "base_url": "https://api.example.com/v1",
    "api_key": "...",
    "model": "chat-model-name",
    "temperature": 0.2,
    "timeout_seconds": 60
}
```

Embedding 配置：

```python
embedding_config = {
    "base_url": "https://api.example.com/v1",
    "api_key": "...",
    "model": "embedding-model-name",
    "timeout_seconds": 60
}
```

字段要求：

- `base_url`、`api_key`、`model` 必填。
- `temperature` 只用于 chat model。
- `timeout_seconds` 可选；未传时由调用方封装默认值后再传入，不在 `main/src` 内部硬编码。
- 配置缺失必须直接报错。

### 6.2 RAG 构建函数

新增 RAG 构建模块，例如 `rag_builder.py`，对外提供：

```python
def build_or_update_rag_database(
    raw_docs_dir: str,
    chroma_db_path: str,
    manifest_path: str,
    parsed_cache_dir: str,
    chunk_cache_dir: str,
    llm_config: dict,
    embedding_config: dict,
) -> tuple[int, str, dict]:
    ...
```

参数含义：

| 参数 | 含义 |
| :--- | :--- |
| `raw_docs_dir` | 医生资料目录，只需放 PDF |
| `chroma_db_path` | ChromaDB 持久化目录 |
| `manifest_path` | 资料库索引状态文件 |
| `parsed_cache_dir` | PDF 解析缓存目录 |
| `chunk_cache_dir` | 结构化知识块缓存目录 |
| `llm_config` | 大模型结构化知识块配置 |
| `embedding_config` | embedding 模型配置 |

返回数据至少包含：

```json
{
  "indexed_files": 2,
  "skipped_files": 5,
  "deleted_files": 1,
  "chunk_count": 86
}
```

接口规范：

- 函数不使用默认目录。
- 函数不读取环境变量。
- 函数不创建测试样本。
- 函数只处理 `raw_docs_dir` 中调用方提供的文件。
- 函数必须返回构建统计信息。
- 函数失败时返回 `status_code = 0` 和明确错误信息。

### 6.3 教学反馈主函数

`ai_processor.py` 对外提供一个主入口：

```python
def generate_teaching_feedback_report(
    scoring_data: dict,
    rubric_text: str,
    case_info: dict,
    prompt_text: str,
    chroma_db_path: str,
    llm_config: dict,
    embedding_config: dict,
    output_json_path: str | None = None,
) -> tuple[int, str, dict]:
    ...
```

参数含义：

| 参数 | 含义 |
| :--- | :--- |
| `scoring_data` | `evaluator.py` 输出的玩家最终得分对象，由调用方读取 |
| `rubric_text` | 评分细则 Markdown 文本，由调用方读取 |
| `case_info` | 病例文本信息对象，由调用方读取 |
| `prompt_text` | LLM 引导提示词文本，由调用方读取 |
| `chroma_db_path` | ChromaDB 本地持久化路径 |
| `llm_config` | 大模型报告生成配置 |
| `embedding_config` | embedding 检索配置 |
| `output_json_path` | 可选输出路径；如果传入则写文件，否则只返回 dict |

返回值：

```python
(status_code, message, report_data)
```

- `status_code = 1`：生成成功。
- `status_code = 0`：生成失败。
- `message`：成功或失败原因。
- `report_data`：教学反馈 JSON 对象。

接口规范：

- 函数不读取固定评分文件。
- 函数不读取固定 prompt 文件。
- 函数不读取固定病例文件。
- 函数不从环境变量获取模型配置。
- 函数不写死 ChromaDB 目录。
- 函数可以在 `output_json_path` 不为空时写出报告，但路径必须由调用方传入。
- `scoring_data` 中的分数是唯一计分真值。

### 6.4 输出 JSON 结构

AI 教学反馈输出只保留三个字段，前端直接展示这三段内容：

```json
{
  "advantage": "你这次覆盖范围和点位均匀性表现稳定，覆盖范围得分为 35/35，点位均匀性得分为 30/30，说明治疗区域覆盖完整，打点间距控制较稳。",
  "disadvantage": "主要问题是激光参数空间适配度不足，该项得分为 24.03/35。曝光时间得分为 4.79/8，波长得分为 5.19/8，偏差集中在上方左侧区域，可能导致局部凝固反应不均或治疗效应不足。",
  "improvement": "下次重点复盘上方左侧区域的曝光时间和波长设置，对照 error_exposure_time_heatmap 与 error_wavelength_map，观察高误差区域是否消失；推进打点时继续保持约一个光斑直径的间距，把重叠次数从 4 次降到 0 次。"
}
```

### 6.5 字段约束

- 输出 JSON 只能包含 `advantage`、`disadvantage`、`improvement` 三个顶层字段。
- 不允许输出 `session_id`、`task_id`、`total_score`、`dimension_scores`、`visualization_references`、`rag_references` 或任何其他字段。
- 三个字段的值必须是字符串，不允许是数组或对象。
- `advantage` 只写 1 到 2 个关键优点，必须引用评分 JSON 中已有分数或事实。
- `disadvantage` 优先写最低得分项，必须引用评分 JSON 中已有分数、平均误差或主要偏差区域。
- `improvement` 必须给出至少 2 个可执行动作，并包含观察指标。
- 分数、平均误差、主要偏差区域、热力图路径只能来自评分 JSON，不允许模型改写或伪造。

## 7. Prompt 约束

现有 `llm_structured_scoring_report_prompt.txt` 需要从自然语言报告改为 JSON 输出约束。

核心约束：

- 只输出合法 JSON，不输出 Markdown、解释文字或代码块。
- 不得修改任何评分数字。
- 不得补造评分 JSON 中没有的错误。
- 不得出现面向学员无意义的算法术语，例如 `IoU`、`R值`、`阈值`、`线性插值`。
- 可以使用面向学员的表达，例如覆盖范围、激光参数空间适配度、参数热力图、局部参数偏差、点位均匀性、重叠扣分。
- 缺点必须优先选择得分占比最低的项目。
- 每个问题反馈必须包含现象、机制、临床后果。
- 每条改进建议必须包含具体动作、背后原理、观察指标。
- 若最低得分项来自维度二，必须优先解释 `sub_scores` 中得分最低或 `mean_error` 最高的参数，并结合 `main_error_regions` 和 `visualization` 给出可观察复盘指标。
- RAG 内容只能作为医学解释依据，不能覆盖评分 JSON。

输入消息建议结构：

```text
系统角色：
你是视网膜光凝教学带教医生，只输出严格 JSON。

评分结果：
{scoring_json}

病例信息：
{case_info_json}

评分细则摘要：
{rubric_summary}

RAG 临床知识：
{retrieved_chunks}

输出 schema：
{json_schema}
```

## 8. 测试方案

### 8.1 `test/src` 全链路模拟规范

`evaluation/test/src` 必须打通完整链路，并作为上层模块调用 `main/src` 的参考样例。测试层允许写死测试样本路径和输出路径，但所有路径与模型参数必须集中写在 `evaluation/test/src/config.json`，不分散硬编码在多个脚本里。

测试层包含两个入口脚本：

- `build_rag.py`：只负责 RAG 向量数据库构建与自检查。
- `test_evaluator.py`：负责完整评测链路，即本地规则评分 + AI 教学反馈生成。

两者共同读取同一个 `config.json`。

### 8.2 `test/src/config.json` 规范

配置文件位置：

```text
evaluation/test/src/config.json
```

配置职责：

- 管理 API base URL、API key、chat model、embedding model。
- 管理 RAG 原始资料目录、缓存目录、ChromaDB 目录、manifest 路径。
- 管理当前测试样本输入路径。
- 管理评分细则、提示词、输出路径。

推荐结构：

```json
{
  "llm": {
    "base_url": "https://api.example.com/v1",
    "api_key": "YOUR_API_KEY",
    "model": "chat-model-name",
    "temperature": 0.2,
    "timeout_seconds": 60
  },
  "embedding": {
    "base_url": "https://api.example.com/v1",
    "api_key": "YOUR_API_KEY",
    "model": "embedding-model-name",
    "timeout_seconds": 60
  },
  "rag": {
    "raw_docs_dir": "evaluation/test/rag/raw_docs",
    "parsed_cache_dir": "evaluation/test/rag/parsed_cache",
    "chunk_cache_dir": "evaluation/test/rag/chunk_cache",
    "chroma_db_path": "evaluation/test/rag/chroma_db",
    "manifest_path": "evaluation/test/rag/rag_manifest.json"
  },
  "inputs": {
    "sample_root": "evaluation/test/sample_data/Temp770298_sample_v4",
    "case_info_json_path": "evaluation/test/sample_data/Temp770298_sample_v4/R/770298_introduction.json",
    "rubric_md_path": "evaluation/docs/评分细则v4.md",
    "prompt_path": "evaluation/docs/llm_structured_scoring_report_prompt.txt",
    "base_scoring_config_path": "evaluation/docs/config.json"
  },
  "outputs": {
    "runtime_scoring_config_path": "evaluation/test/output/Temp770298_sample_v4/runtime_config_for_test.json",
    "scoring_output_json_path": "evaluation/test/output/Temp770298_sample_v4/score_result.json",
    "teaching_feedback_json_path": "evaluation/test/output/Temp770298_sample_v4/teaching_feedback.json"
  }
}
```

规范：

- `config.json` 属于测试调用层配置，不属于 `main/src`。
- `main/src` 只接收 `config.json` 里解析出来的参数，不直接读取该文件。
- 路径可以是相对项目根目录路径，测试脚本负责转换为绝对路径后传给 `main/src`。
- API 配置缺失时测试脚本必须直接报错。
- 不在 `build_rag.py` 或 `test_evaluator.py` 中散落重复配置。

### 8.3 `build_rag.py` 流程

脚本位置：

```text
evaluation/test/src/build_rag.py
```

职责：

- 读取 `evaluation/test/src/config.json`。
- 从配置中取得 RAG 路径和模型配置。
- 调用 `evaluation/main/src/rag_builder.py` 中的 `build_or_update_rag_database(...)`。
- 对构建结果做必要自检查。
- 不执行评分，不生成教学反馈。

流程：

```text
读取测试配置
  -> 调用 rag_builder.build_or_update_rag_database(...)
  -> 检查返回 status_code
  -> 检查 ChromaDB 目录存在
  -> 检查 rag_manifest.json 存在
  -> 检查 indexed/skipped/deleted/chunk_count 统计字段存在
  -> 检查至少有可检索 chunk
  -> 输出构建摘要
```

自检查要求：

- `raw_docs_dir` 必须存在。
- `raw_docs_dir` 下至少有一个 PDF，否则直接报错。
- `chroma_db_path` 构建后必须存在。
- `manifest_path` 构建后必须存在。
- manifest 中每个已索引文件必须包含 `sha256`、`indexed_at`、`chunk_count`、`status`。
- `chunk_count` 必须大于 0。
- 随机检索一次与眼底光凝相关的 query，必须返回至少 1 条结果。

准备一个或多个测试 PDF 放入：

```text
evaluation/test/rag/raw_docs/
```

这是测试目录示例。正式调用时，资料目录由上层模块传入。

构建模块必须通过以下测试：

- `chroma_db/` 不存在时能全量构建。
- `rag_manifest.json` 不存在时能创建。
- PDF 未变化时二次运行必须跳过，不重复入库。
- 新增 PDF 后只索引新增文件。
- 修改 PDF 后删除旧 chunk 并重新索引该文件。
- 删除 PDF 后删除 ChromaDB 中该文件对应 chunk。
- 每个 chunk 必须包含 `source_file`、`page_start`、`page_end`、`text`。
- LLM 输出非法 JSON、PDF 无法解析、embedding 失败时直接报错。

### 8.4 `test_evaluator.py` 全链路流程

脚本位置：

```text
evaluation/test/src/test_evaluator.py
```

职责：

- 读取 `evaluation/test/src/config.json`。
- 根据 `sample_root` 自动定位玩家操作日志和病例手术 GT 参数文件。
- 调用 `evaluator.evaluate(...)` 完成本地规则评分。
- 读取评分结果 JSON。
- 读取病例文本信息、评分细则、提示词。
- 读取 RAG 向量数据库位置和模型配置。
- 调用 `ai_processor.generate_teaching_feedback_report(...)` 生成教学反馈 JSON。
- 在 `evaluation/test/output/` 同时保存玩家得分 JSON 和教学反馈 JSON。

输入内容：

- 病例文本信息：`case_info_json_path`。
- 玩家操作日志：由 `sample_root` 自动定位 `_simplayer.json`。
- 病例手术 GT 参数：由 `sample_root` 自动定位 `_simgt.json`。
- 评分细则：`rubric_md_path`。
- RAG 向量数据库位置：`rag.chroma_db_path`。
- 提示词：`prompt_path`。
- 评分配置：`base_scoring_config_path`，测试脚本可生成 runtime config 后传给 `evaluator.py`。
- 维度二空间参数配置：测试脚本需要在 runtime config 中注入 `param_tolerance_abs` 和 `spatial_parameter_field`，例如功率容忍值、光斑直径容忍值、曝光时间容忍值和参数场影响半径。
- LLM 配置和 embedding 配置：从 `config.json` 读取后显式传给 `main/src`。

流程：

```text
读取 config.json
  -> 校验 RAG 向量数据库已存在
  -> 自动定位 question_json_path 和 player_json_path
  -> 生成 runtime scoring config
  -> 调用 evaluator.evaluate(...)
  -> 保存玩家得分 JSON
  -> 读取 scoring_data / rubric_text / case_info / prompt_text
  -> 调用 ai_processor.generate_teaching_feedback_report(...)
  -> 保存教学反馈 JSON
  -> 校验两个输出文件存在且 JSON 可解析
```

输出文件：

```text
evaluation/test/output/Temp770298_sample_v4/score_result.json
evaluation/test/output/Temp770298_sample_v4/teaching_feedback.json
```

要求：

- `test_evaluator.py` 不负责构建 RAG；RAG 必须先由 `build_rag.py` 构建。
- 如果 RAG 向量数据库不存在，`test_evaluator.py` 直接报错，提示先运行 `build_rag.py`。
- `test_evaluator.py` 可以作为游戏后端调用 `main/src` 的参考实现。
- 本地评分成功但 AI 报告失败时，必须保留玩家得分 JSON，并明确报错 AI 失败原因。

### 8.5 教学反馈测试样本

使用当前样本：

```text
evaluation/test/output/Temp770298_sample_v4/score_result.json
evaluation/docs/评分细则v4.md
evaluation/test/sample_data/Temp770298_sample_v4/R/770298_introduction.json
evaluation/docs/llm_structured_scoring_report_prompt.txt
```

### 8.6 必须保留的评分事实

AI 输出必须保留以下事实：

| 指标 | 期望值 |
| :--- | :--- |
| 总分 | `85.03/100` |
| 覆盖范围 | `35/35` |
| 激光参数空间适配度 | `24.03/35` |
| 功率 | `7.61/11`，平均误差 `0.3078` |
| 光斑直径 | `6.44/8`，平均误差 `0.1945` |
| 曝光时间 | `4.79/8`，平均误差 `0.4018`，主要偏差区域 `上方左侧曝光时间偏差较高` |
| 波长 | `5.19/8`，平均误差 `0.3516`，主要偏差区域 `上方左侧波长偏差较高` |
| 点位均匀性 | `30/30` |
| 光斑重叠 | `4` 次 |
| 病例诊断 | `视网膜裂孔` |

若 LLM 输出的数字与评分 JSON 不一致，应判定失败。

### 8.7 JSON 校验

测试时必须检查：

- 输出能被 `json.loads()` 正常解析。
- 顶层字段必须且只能包含 `advantage`、`disadvantage`、`improvement`。
- 三个字段的值必须都是字符串。
- `advantage` 必须包含至少一个评分事实，例如 `35/35` 或 `30/30`。
- `disadvantage` 必须优先出现激光参数空间适配度不足，并包含至少一个评分事实，例如 `24.03/35`、`4.79/8` 或 `5.19/8`。
- 若引用维度二问题，`disadvantage` 或 `improvement` 必须包含至少一个 `main_error_regions` 中的区域描述，当前样本应包含 `上方左侧`。
- `improvement` 必须包含至少两个可执行动作，并至少一个观察指标，例如 `error_exposure_time_heatmap`、`error_wavelength_map` 或 `重叠次数从 4 次降到 0 次`。

### 8.8 RAG 命中校验

当前样本的 RAG 命中结果至少包含：

- 激光参数空间策略或参数场适配相关知识。
- 曝光时间偏差与局部热损伤或凝固反应不均相关知识。
- 波长选择与组织吸收特性相关知识。
- 光斑重叠导致局部热量堆积的风险。

如果没有命中这些知识，说明 query 生成或知识块标签设计存在问题。

## 9. 后续优化顺序

当前 1-6 步基础链路已经完成，后续建议继续优化：

1. 用更多医生资料扩充 `raw_docs/`，覆盖视网膜裂孔、格子样变性、糖网、静脉阻塞等场景。
2. 在 `rag_builder.py` 中增加 LLM 结构化知识块能力，把规则切块升级为“原文页码 + 标题 + 标签 + 摘要 + 正文”的稳定知识单元。
3. 优化 RAG query 生成，把最低得分项、扣分项、病例诊断和热力图异常区域映射到更稳定的 `score_tags`。
4. 增加 RAG 命中报告，方便调试每次反馈引用了哪些知识块。
5. 给 `build_rag.py` 增加更严格的回归测试：新增 PDF、修改 PDF、删除 PDF、二次运行跳过未变化文件。
6. 后续由游戏后端按同样方式接入 `main/src` 模块。

## 10. 关键假设

- 当前阶段已经开始实现并联调 `ai_processor.py`、`rag_builder.py`、`main.py` 和测试脚本。
- 第一阶段 RAG 资料来源为医生提供的 PDF 电子书和 PDF 课件，不手写知识库，不放专家案例库。
- AI 报告先服务当前视网膜裂孔样本，后续再扩展糖尿病视网膜病变、格子样变性等更多疾病类型。
- 真实 API key、模型名、base_url 可以由上层从环境变量读取，但必须作为显式配置传入 `main/src`。
- 若 PDF 解析失败、模型调用失败、RAG 索引不存在、embedding 失败或模型返回非法 JSON，应直接报错暴露问题，不做静默兜底。
