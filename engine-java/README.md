# Engine-Java

Java 模块（规则引擎）初始化说明

目标：使用 Maven 管理，构建时自动从 `shared/protos` 生成 Java POJO（通过 `protoc-jar-maven-plugin`），并成为可运行的 Spring Boot 服务。

快速上手

1. 在仓库根目录运行 Maven 构建（会在 generate-sources 阶段调用 protoc-jar）：

```bashpavk
cd services/engine-java
mvn clean package
```

1. 如果成功，生成的 protobuf Java 源会放在：

```
services/engine-java/target/generated-sources/protobuf/java
```

1. 运行服务（本地）：

```bash
mvn spring-boot:run
# 或运行打包后的 jar
java -jar target/engine-java-0.1.0-SNAPSHOT.jar
```

注意

- `pom.xml` 使用 `protoc-jar-maven-plugin` 在 `generate-sources` 阶段运行 `protoc`，从 `../shared/protos` 中读取 `.proto` 文件并生成 Java 源。
- 如果需要同时生成 gRPC stub（`grpc-java`），需要为 `protoc` 提供 `protoc-gen-grpc-java` 插件并在 `protocArgs` 中指定 `--grpc-java_out`；当前配置至少会生成 Java POJO。

如需我把 gRPC 代码生成也加入到构建流程（并示例集成 gRPC server stub），我可以继续补充。

# 项目相关说明

1. 传入的数据结构：

    示例
    {
    "doc_id": "paper_2024_001",
    "metadata": {
    "title": "基于AI的文档审查研究",
    "total_pages": 24,
    "global_style": { "font": "SimSun", "line_spacing": 1.5 }
    },
    "sections": [
    {
    "section_id": 1,
    "type": "heading",
    "level": 1,
    "text": "1. 引言",
    "properties": { "font_size": 16, "bold": true, "before_spacing": 12 }
    },
    {
    "section_id": 2,
    "type": "paragraph",
    "text": "随着人工智能的发展，文档审查变得尤为重要[1]。",
    "citations": ["[1]"],
    "properties": { "first_line_indent": 2.0 }
    }
    ],
    "references": [
    { "ref_id": "[1]", "raw_text": "[1] 张三. 人工智能导论[M]. 北京: 科学出版社, 2023." }
    ]
    }
    1. 根对象结构：
       {
       "doc_id": "paper_2024_001", // 文档唯一标识
       "metadata": {...}, // 文档元数据
       "sections": [...], // 文档章节列表
       "references": [...] // 参考文献列表
       }

    2. Metadata（元数据）：
       "metadata": {

    "title": "基于AI的文档审查研究", // 文档标题
    "total_pages": 24, // 总页数
    "global_style": { // 全局样式
    "font": "SimSun", // 字体
    "line_spacing": 1.5 // 行间距
    }
    } 3. Section（章节id）:
    {
    "section_id": 1, // 章节ID
    "type": "heading", // 类型：heading/paragraph/table/figure
    "level": 1, // 标题层级（1为一级标题）
    "text": "1. 引言", // 文本内容
    "citations": ["[1]"], // 引用标记数组
    "properties": { // 样式属性
    "font_size": 16, // 字体大小
    "bold": true, // 是否加粗
    "before_spacing": 12 // 段前间距
    }
    } 4. Reference（参考文献）:
    {
    "ref_id": "[1]", // 引用ID，如 [1]
    "raw_text": "[1] 张三. 人工智能导论[M]. 北京: 科学出版社, 2023."
    }

2. Issue 数据结构：

message Issue {
string code = 1; // 错误代码，如 "ERR_FONT_001"
string message = 2; // 给用户的错误描述
int32 section_id = 3; // 关联的段落 ID
Severity severity = 4; // 严重程度
string suggestion = 5; // 修改建议
string original_snippet = 6; // 原始错误文本片段
}

''''
Issue issue = Issue.newBuilder()
.setCode("ERR_FONT_HEADING") 设置 code 字段
.setMessage("标题字体应为黑体或微软雅黑") 设置 message 字段
.setSectionId(section.getSectionId()) 设置 section_id 字段
.setSeverity(Severity.MEDIUM) 设置 severity 字段
.setSuggestion("修改字体为黑体") 设置 suggestion 字段
.setOriginalSnippet(section.getText().substring(0, 设置 original_snippet 字段
Math.min(section.getText().length(), 50)))
.build();
''''

错误代码
"ERR_FONT_NULL":输入数据为空
"ERR_FONT_HEADING":标题错误

## AuditResponse 结构

{
"issues": [
{
"type": "string", // 问题类型
"description": "string", // 问题描述
"location": "string", // 位置（可选）
"suggestion": "string", // 建议（可选）
"severity": "enum", // 严重级别：LOW/MEDIUM/HIGH/CRITICAL
"scoreImpact": "float", // 单个问题扣分
"timestamp": "int64", // 时间戳
"module": "string" // 审计模块
}
],
"scoreImpact": "float" // 总分扣分
}
