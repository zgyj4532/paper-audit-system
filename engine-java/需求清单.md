# 📄 需求文档：核心规则引擎与数据一致性中枢 (Java 模块)

## 1. 任务概述

成员 B 负责构建一套基于工业级规则引擎的审查系统。该模块需接收来自 Rust 模块的结构化数据，通过预设的学术规范算法（GB/T 7714、APA 等）进行高精度的排版校验和引用闭环一致性检查。

## 2. 技术栈要求

* **核心语言：** **Java 21**（利用虚拟线程 Virtual Threads 处理高并发审查任务）。
* **框架：** **Spring Boot 3.x** + **Spring Batch**（用于大文件分批处理）。
* **规则引擎：** **Drools 8.0+**（实现业务逻辑与代码解耦）。
* **数据库/缓存：** **Redis**（缓存常用模板规则）+ **PostgreSQL**（存储审计历史）。
* **通讯：** **gRPC (Stubby)**。

---

## 3. 核心功能模块与执行清单

### 模块一：基于 Drools 的排版规则引擎 (Formatting Auditor)

* **需求描述：** 将学校或国家的排版细则转化为可编程规则。
* **任务拆解：**
* **层级检测：** 校验标题序列（Heading 1 -> Heading 2）。
* **视觉参数校验：** 比对 `Section.props` 中的 `font-size`、`font-family`、`line-height` 是否符合目标模板。
* **图表逻辑：** 检查表格是否跨页断开但未设置“续表”标志；公式是否右对齐。

* **执行清单：** 编写 `.drl` 规则文件，实现规则的动态加载与热更新。

### 模块二：引用闭环一致性校验器 (Reference Consistency Checker)

* **需求描述：** 确保“正文引用点”与“文末参考文献”形成完美的  映射。
* **任务拆解：**
* **双向追溯：** 扫描 `sections` 中的所有引用锚点，构建指向 `references` 的有向图。
* **排序校验：** 针对 GB/T 7714 顺序编码制，检测正文引用序号是否按出现先后排序。
* **格式完整性：** 检查参考文献条目是否缺失核心要素（如：[M] 类文献是否缺失出版地）。

* **执行清单：** 实现一个基于位图（Bitmap）或哈希比对的快速对齐算法。

### 模块三：必备章节完整性状态机 (Document Integrity Scan)

* **需求描述：** 验证文档是否包含所有法定章节。
* **任务拆解：**
* 定义不同文档类型的“必选项”（如学位论文必须有致谢，期刊论文不必）。
* **语义触发：** 根据 `Section.text` 的模糊匹配确定章节性质。

* **执行清单：** 编写一套状态机逻辑，输出缺失章节的 `CRITICAL` 级别错误。

---

### 4. 关键算法逻辑 (Drools 示例)

成员 B 需维护类似下方的规则代码，确保非技术人员（如教务处）未来也能调整参数：

```java
rule "检查一级标题字体"
    when
        $s : Section(type == "heading", level == 1, props["font-family"] != "SimHei")
    then
        Issue issue = new Issue();
        issue.setCode("ERR_FONT_001");
        issue.setMessage("一级标题必须使用黑体");
        issue.setSeverity(Severity.MEDIUM);
        insert(issue);
end

```

---

### 5. 接口契约与数据对齐

成员 B 需严格遵守 `auditor.proto` 协议，特别是对 `Issue` 对象的填充：

| 输入对象 (ParsedData) | 处理逻辑 | 输出对象 (AuditResponse) |
| --- | --- | --- |
| `sections` 列表 | 迭代校验 `props` | `Issue` 列表 (关联 section_id) |
| `references` 列表 | 与正文文本进行交叉比对 | `Issue` (标注缺失或多余引用) |
| `metadata` | 校验页边距与全局样式 | `Issue` (定位至 metadata 级别) |

---

### 6. 成员 B 的阶段性 KPI

1. **第一周：** 搭建 Spring Boot + gRPC 服务骨架，完成与成员 D (Go) 的握手测试。
2. **第二周：** 开发 GB/T 7714 参考文献基础校验算法，准确率需 > 98%。
3. **第三周：** 集成 Drools 引擎，完成至少 50 条排版规则的硬编码转换。
4. **第四周：** 压力测试。确保在 **Virtual Threads** 开启下，单台容器能同时处理 100 个审查请求。

---

### 💡 协作建议

**成员 B 请注意：** 你是系统逻辑最重的地方。

* 请务必为每条规则编写 **Unit Test**，防止修改 APA 规则时意外破坏了 GB/T 7714 的逻辑。
* 由于 Rust 解析出的数据可能存在噪点，你的代码必须具备极强的**容错性 (Fault Tolerance)**。
