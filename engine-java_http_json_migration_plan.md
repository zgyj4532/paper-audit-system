# engine-java 规则引擎替换与 HTTP/JSON 统一对接方案

## 一、目标

将当前 Python 中的 rules 规则引擎逐步替换为可运行的 `engine-java` 服务，统一通过 HTTP/JSON 对接，避免 Python 侧继续直接维护规则实现。最终目标是：

1. Python 只保留工作流编排、任务调度、文档解析、AI 评审编排和结果汇总。
2. Java 统一承接排版、参考文献、一致性、完整性等规则审查。
3. Python 与 Java 的交互从 gRPC 过渡到 HTTP/JSON，便于调试、联调、测试和后续扩展。
4. 实际测试阶段关闭 AI 评审功能，优先验证规则引擎迁移是否正确、稳定、可回归。

> 说明：这里的“rgpc”按 gRPC 理解；当前方案以 HTTP/JSON 为唯一业务对接方式，gRPC 可作为过渡期内部保留能力，但不作为 Python 主调用路径。

## 二、现状与问题

当前工程里，Python 侧的规则入口已经拆成了多个模块，主要位于 [python_service/paper_audit/services/rules](python_service/paper_audit/services/rules)；工作流层在 [python_service/paper_audit/services/workflow/langgraph.py](python_service/paper_audit/services/workflow/langgraph.py) 里直接调用这些规则函数。与此同时，`engine-java` 已经具备 Java 规则审查实现，并且当前提供了 gRPC 审查入口和 HTTP 服务端口，但 Python 并未直接通过 HTTP/JSON 接入它。

这带来三个问题：

1. 规则逻辑分散在 Python 和 Java 两边，后续维护成本高。
2. Python 侧直接调用本地规则函数，无法统一做接口治理、版本控制和请求审计。
3. gRPC 对联调和排障并不如 HTTP/JSON 直观，尤其是跨语言排查问题时。

## 三、总体规划

### 3.1 目标架构

建议采用“Python 编排 + Java 规则引擎 + HTTP/JSON 传输”的分层结构：

1. Python 负责接收上传、任务队列、文档解析、AI 审查、报告生成。
2. Python 在进入规则阶段时，只调用一个统一的 Java HTTP 客户端。
3. Java 暴露一个稳定的规则审查 HTTP 接口，由该接口承接当前 gRPC 服务内部的规则实现。
4. Java 返回统一的 `issues` 和 `score_impact`，Python 只做结果归并和展示。

### 3.2 迁移分期

建议分四期实施：

1. 评估期：梳理 Python 现有规则调用点、Java 现有规则能力、输入输出数据契约。
2. 适配期：在 Java 侧补出 HTTP/JSON 入口，在 Python 侧补出 HTTP 客户端和统一适配层。
3. 切换期：Python 工作流默认改走 Java HTTP，保留本地规则作为临时回退或对照模式。
4. 清理期：确认稳定后，删除 Python 中直接承载规则判断的实现，只保留少量数据清洗与格式转换逻辑。

### 3.3 接口边界

推荐将接口边界固定为三类消息：

1. 输入：`ParsedData` 等价 JSON。
2. 请求：`AuditRequest` 等价 JSON，包含 `data`、`target_rule_set`、`trace_id`、`source_file` 等可选元数据。
3. 输出：`AuditResponse` 等价 JSON，包含 `issues`、`score_impact`、`engine_version`、`elapsed_ms` 等元数据。

这样可以同时兼容后续继续保留 gRPC 的内部调用，也可以直接用 HTTP/JSON 做跨语言调用。

Rust 的输出样例可直接参考 [outputs/report_71.json](outputs/report_71.json)。其中最关键的结构是 `parse_result.data.metadata` 和 `parse_result.data.sections`：

1. `metadata.total_pages`、`metadata.total_paragraphs`、`metadata.total_tables`、`metadata.total_words` 适合作为解析结果摘要字段。
2. `sections[]` 适合作为 Java 规则引擎的输入数据源，字段中至少应保留 `id`、`element_type`、`raw_text`、`formatting`、`level`、`coordinates`、`position`、`xml_path` 和 `is_table`。
3. `ai_review.backend`、`reference_verification.llm_backend`、`chunk_reviews.backend`、`issues_count` 适合作为最终报告汇总字段。

### 3.4 接口字段对照表

下表用于统一 Python、Java 和 Rust 三侧的 JSON 字段命名。实际实现时建议以这个映射作为最小公共契约。

| 场景 | 来源字段 | 目标字段 | 说明 |
| --- | --- | --- | --- |
| Rust 解析输出 | `parse_result.data.metadata.total_pages` | `document.page_count` | 解析页数摘要 |
| Rust 解析输出 | `parse_result.data.metadata.total_paragraphs` | `document.paragraph_count` | 段落数量摘要 |
| Rust 解析输出 | `parse_result.data.metadata.total_tables` | `document.table_count` | 表格数量摘要 |
| Rust 解析输出 | `parse_result.data.metadata.total_words` | `document.word_count` | 字数摘要 |
| Rust 解析输出 | `parse_result.data.sections[]` | `parsed_sections[]` | 规则引擎输入主数组 |
| Rust 解析输出 | `sections[].id` | `section_id` | 节点唯一标识 |
| Rust 解析输出 | `sections[].element_type` | `type` | 段落、表格、标题、公式等 |
| Rust 解析输出 | `sections[].raw_text` | `text` | 规则匹配文本 |
| Rust 解析输出 | `sections[].formatting` | `style` | 字体、字号、缩进、对齐等 |
| Rust 解析输出 | `sections[].level` | `outline_level` | 章节层级 |
| Rust 解析输出 | `sections[].coordinates` | `layout` | 页码、坐标、行列位置 |
| Java 规则输入 | `document + parsed_sections + config` | `AuditRequest` | 统一 HTTP 入参 |
| Java 规则输出 | `issues[]` | `audit_issues[]` | 规则命中结果 |
| Java 规则输出 | `score_impact` | `risk_summary.score_impact` | 风险分数变化 |
| Java 批注输出 | `annotated_docx_path` | `annotation.output_path` | Rust 批注回写结果 |
| Python 汇总输出 | `issues_count` | `report.summary.issues_count` | 最终问题数 |

### 3.5 请求样例与返回样例

#### Rust -> Java 规则审查请求样例

```json
{
 "document": {
  "doc_id": "paper-2026-00071",
  "file_name": "sample.docx",
  "page_count": 28,
  "paragraph_count": 362,
  "table_count": 4,
  "word_count": 15682
 },
 "parsed_sections": [
  {
   "section_id": "p-001",
   "type": "paragraph",
   "outline_level": 0,
   "text": "Abstract:This paper studies panoramic simulation.",
   "style": {
    "font_family": "Times New Roman",
    "font_size": 12,
    "alignment": "left"
   },
   "layout": {
    "page_number": 1,
    "x": 72,
    "y": 108
   }
  }
 ],
 "config": {
  "enabled_rules": ["format", "logic", "reference"],
  "strictness": 3,
  "fast_local_only": true
 }
}
```

#### Java 规则审查返回样例

```json
{
 "status": "ok",
 "doc_id": "paper-2026-00071",
 "rule_engine": "drools",
 "issues": [
  {
   "issue_id": "FORMAT-004-0001",
   "rule_code": "FORMAT-004",
   "severity": "medium",
   "section_id": "p-001",
   "message": "Abstract 后缺少空格",
   "suggestion": "将 'Abstract:This' 改为 'Abstract: This'"
  }
 ],
 "score_impact": {
  "total": -2,
  "format": -2,
  "logic": 0,
  "reference": 0
 },
 "summary": {
  "issue_count": 1,
  "high_risk_count": 0,
  "medium_risk_count": 1,
  "low_risk_count": 0
 }
}
```

#### Java -> Rust 批注写回请求样例

```json
{
 "doc_id": "paper-2026-00071",
 "source_docx_path": "./uploads/sample.docx",
 "issues": [
  {
   "issue_id": "FORMAT-004-0001",
   "section_id": "p-001",
   "message": "Abstract 后缺少空格",
   "severity": "medium",
   "suggestion": "将 'Abstract:This' 改为 'Abstract: This'"
  }
 ],
 "output_path": "./outputs/sample_annotated.docx"
}
```

#### Rust -> Java 批注写回返回样例

```json
{
 "status": "ok",
 "annotated_docx_path": "./outputs/sample_annotated.docx",
 "annotated_comment_count": 1,
 "warning_count": 0
}
```

## 四、初步实现方案

### 4.1 Java 侧实现

Java 侧建议新增一个 HTTP 规则审查控制器，将当前规则审查服务封装成对外 REST 接口。做法如下：

1. 新增 `RuleAuditController` 或等价接口层，暴露 `POST /api/v1/rules/audit`。
2. 复用现有规则引擎服务层，不要把规则逻辑写进 Controller。
3. 让 gRPC 的 `AuditRules` 实现和 HTTP Controller 都委托同一个内部 service，避免双份逻辑。
4. 返回 JSON 结构与现有 `Issue` / `AuditResponse` 一致，字段至少包含 `code`、`message`、`section_id`、`severity`、`suggestion`、`original_snippet`。
5. 增加 `/health` 或 `/actuator/health` 检查，便于 Python 在启动时做连通性探测。

### 4.2 Python 侧实现

Python 侧建议把当前规则引擎入口改成统一适配层，而不是工作流里直接调用具体函数：

1. 在 `python_service/paper_audit/services/rules/engine.py` 中增加 Java HTTP 调用入口，作为主路径。
2. 保留本地规则函数作为临时 fallback 或单元测试对照，不再作为默认执行路径。
3. 让 [python_service/paper_audit/services/workflow/langgraph.py](python_service/paper_audit/services/workflow/langgraph.py) 只依赖一个“规则审查入口”，不要再直接依赖多个本地规则模块。
4. 对外统一暴露一个 backend 选择策略，例如 `java_http`、`local`、`hybrid`。
5. 在返回结果中保留原始 Java 响应，方便排障和对账。

### 4.3 迁移策略

建议采用“双轨对照、单轨生效”的方式：

1. 第一阶段：Python 同时能调用本地规则和 Java HTTP，但业务结果以 Java 为准。
2. 第二阶段：Python 默认只调用 Java HTTP，本地规则只在测试模式下保留。
3. 第三阶段：确认 Java 结果稳定后，删除 Python 中不再需要的规则实现。

这样可以最大限度降低切换风险，避免一次性替换造成大面积回归。

### 4.4 一键启动可行性

Java 可以和 Rust 一样整合到根目录的 `main.py` 中做一键启动，但更准确地说，真正的编排点应放在 Python 服务入口里，再由根目录 `main.py` 进行转发。当前根目录入口只是薄封装，真正承担启动逻辑的是 [python_service/paper_audit/main.py](python_service/paper_audit/main.py)。

结论如下：

1. 技术上可行，可以用 Python 统一拉起 Rust 和 Java 两个子进程。
2. 现有 Python 启动逻辑已经支持 Rust 自动启动，Java 可以复用同样的生命周期管理方式。
3. 建议保留开关参数，例如 `--no-java`、`--skip-java-build`、`--java-release`，避免开发调试时强依赖 Java 二进制存在。
4. 生产环境更建议由 Docker Compose、systemd 或独立守护进程启动，Python 只负责业务编排，不负责长期托管所有子服务。

如果要实现真正的一键启动，推荐按以下顺序：

1. 先启动 Rust，确保 `/parse` 和 `/annotate` 可用。
2. 再启动 Java，确保规则引擎 HTTP 服务就绪。
3. 最后启动 Python，统一接管上传、任务、报告和 AI 审查流程。

这样可以避免 Python 在启动早期就收到不可用依赖，从而降低首次请求失败概率。

## 五、环境搭建

### 5.1 Java 环境

建议环境如下：

1. JDK 21。
2. Maven 3.8+。
3. 本地启动端口：HTTP `8081`，gRPC `9191`。
4. 如使用 Docker，则由 compose 统一注入环境变量和端口映射。
5. 环境变量建议已写入 [.env](.env) 与 [.env.example](.env.example)，至少包括 `ENGINE_JAVA_HTTP_PORT`、`ENGINE_JAVA_GRPC_PORT`、`ENGINE_JAVA_BASE_URL`、`ENGINE_JAVA_JAR_PATH`、`ENGINE_JAVA_MAIN_CLASS`、`ENGINE_JAVA_START_MODE` 和 `ENGINE_JAVA_TIMEOUT_SECONDS`。

### 5.2 Python 环境

建议环境如下：

1. Python 3.11+。
2. 继续使用当前项目已有的 `uv` 或现有虚拟环境。
3. Java 服务地址通过环境变量配置，例如 `ENGINE_JAVA_BASE_URL=http://127.0.0.1:8081`。
4. 测试时关闭 AI 评审：`PAPER_AUDIT_FAST_LOCAL_ONLY=1`。

### 5.3 推荐启动顺序

1. 先启动 `engine-java`，确认 HTTP 健康检查通过。
2. 再启动 Python 服务。
3. 最后用一份固定样例文档做端到端验证。

### 5.4 测试阶段推荐环境变量

为了加快验证，建议在测试阶段使用以下配置：

1. `PAPER_AUDIT_FAST_LOCAL_ONLY=1`：跳过 Qwen 评审路径。
2. `REFERENCE_VERIFIER_BACKEND=local`：引用核验优先走本地召回逻辑。
3. 关闭或不配置 `QWEN_API_KEY`：避免测试阶段误触发外部模型调用。
4. 如需缩短运行时间，可适当降低批次并发参数，但建议保留默认值作为基线。
5. `ENGINE_JAVA_START_MODE=jar`：优先使用已构建好的 Java 产物，减少测试时编译耗时。

## 六、实际测试方案

### 6.1 测试目标

这次测试的重点不是 AI 结果，而是验证规则引擎替换是否成功：

1. Java HTTP 接口可达。
2. Python 能把解析后的结构化数据发给 Java。
3. Java 返回的规则结果能被 Python 正确合并到任务结果中。
4. 在关闭 AI 评审后，整条链路仍能跑通，并且耗时明显降低。

### 6.2 测试步骤

1. 启动 `engine-java`，确认 `/actuator/health` 正常。
2. 用一份固定样例文档跑 Python 审查任务。
3. 通过日志或中间结果确认规则阶段命中了 Java HTTP 接口。
4. 检查最终报告中的问题列表、分数扣减和章节位置是否完整。
5. 使用同一份文档重复执行 3 次，观察结果是否稳定、耗时是否一致。

### 6.3 对照测试

建议保留一轮对照测试：

1. 同一份样例文档先跑旧的本地规则路径，再跑新的 Java HTTP 路径。
2. 对比命中数量、问题类型、严重级别、章节定位和建议文本。
3. 如果存在差异，优先确认是规则逻辑差异还是 JSON 映射差异。

### 6.4 建议的测试用例

至少准备以下四类样例：

1. 正常文档：无明显问题，用于验证误报率。
2. 排版异常文档：标题、字号、行距、页边距、页码等问题明显。
3. 参考文献异常文档：格式不完整、顺序不对、引用缺失。
4. 章节完整性异常文档：缺少摘要、致谢、结论等必备章节。

### 6.5 建议的测试命令

示例命令如下：

```powershell
cd e:\github\paper-audit-system\engine-java
mvn clean test
mvn spring-boot:run
```

```powershell
$env:PAPER_AUDIT_FAST_LOCAL_ONLY="1"
$env:REFERENCE_VERIFIER_BACKEND="local"
python main.py
```

实际请求可优先使用固定样例文件和固定配置，确保测试结果可重复。

## 七、验收条目

### 7.1 功能验收

1. Python 不再直接把规则判断逻辑作为主路径执行，规则审查统一通过 Java HTTP 完成。
2. Java HTTP 接口能接收 `ParsedData` 等价 JSON，并返回完整 `AuditResponse`。
3. 返回结果中 `issues` 的字段结构完整，至少包含 `code`、`message`、`section_id`、`severity`、`suggestion`、`original_snippet`。
4. 规则阶段可覆盖当前已有的排版、参考文献、一致性、完整性等核心检查。
5. 关闭 AI 评审后，任务仍能完整完成，不依赖 Qwen 调用。

### 7.2 质量验收

1. Java HTTP 接口健康检查通过。
2. Python 对 Java 的请求失败时有明确报错，不能静默吞掉。
3. 同一份测试文档多次运行结果稳定。
4. 新旧路径对照结果差异可解释，并能被记录。
5. 文档、示例请求和启动步骤在仓库中可直接复现。

### 7.3 性能验收

1. 关闭 AI 评审后，单次审查耗时应明显低于默认全链路模式。
2. Java 规则接口应支持并发请求，不因单请求阻塞整条工作流。
3. 大文档场景下，规则阶段不应成为不可恢复的瓶颈。

### 7.4 发布验收

1. 已确认 Java HTTP 路径为默认路径。
2. 已保留临时回退策略或明确的切换开关。
3. 已完成至少一轮样例文档回归。
4. 已补充必要的使用说明和排障说明。

## 八、风险与回退

1. 如果 Java HTTP 接口不稳定，可临时切回本地规则路径，确保主流程不阻塞。
2. 如果返回 JSON 结构不一致，优先修正 DTO 映射，而不是修改规则本体。
3. 如果测试结果偏慢，先关闭 AI 评审，再排查 Java 规则接口和 Python 调用链。
4. 如果新旧结果存在差异，先做样例级对账，再决定是否调整规则阈值。

## 九、建议落地顺序

1. 先完成 Java HTTP 接口与 DTO。
2. 再完成 Python 客户端和统一适配层。
3. 然后改造工作流调用点。
4. 接着做关闭 AI 评审的联调测试。
5. 最后整理回归样例并完成清理下线。

---

如果后续要继续推进，我建议下一步直接补一份“接口字段对照表 + 请求样例 + 返回样例”，这样 Java 和 Python 两边可以同步按同一个契约实现。
