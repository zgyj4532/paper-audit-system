use axum::body::{to_bytes, Body};
use axum::http::{Request, StatusCode};
use serde_json::json;
use tower::util::ServiceExt;

fn write_entry(writer: &mut zip::ZipWriter<std::fs::File>, name: &str, content: &str) {
    writer
        .start_file(name, zip::write::SimpleFileOptions::default())
        .unwrap();
    use std::io::Write;
    writer.write_all(content.as_bytes()).unwrap();
}

fn build_minimal_docx(path: &std::path::Path) {
    let file = std::fs::File::create(path).unwrap();
    let mut writer = zip::ZipWriter::new(file);

    write_entry(
        &mut writer,
        "[Content_Types].xml",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"#,
    );

    write_entry(
        &mut writer,
        "_rels/.rels",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"#,
    );

    write_entry(
        &mut writer,
        "word/document.xml",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r><w:t>Hello world</w:t></w:r>
        </w:p>
    </w:body>
</w:document>"#,
    );

    write_entry(
        &mut writer,
        "word/_rels/document.xml.rels",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>"#,
    );

    writer.finish().unwrap();
}

fn build_page_break_docx(path: &std::path::Path) {
    let file = std::fs::File::create(path).unwrap();
    let mut writer = zip::ZipWriter::new(file);

    write_entry(
        &mut writer,
        "[Content_Types].xml",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"#,
    );

    write_entry(
        &mut writer,
        "_rels/.rels",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"#,
    );

    write_entry(
        &mut writer,
        "word/document.xml",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r><w:t>第一段</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>第二段</w:t></w:r>
            <w:r><w:br w:type="page"/></w:r>
            <w:r><w:t>第三段</w:t></w:r>
        </w:p>
        <w:tbl>
            <w:tr>
                <w:tc><w:p><w:r><w:t>R1C1</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>R1C2</w:t></w:r></w:p></w:tc>
            </w:tr>
            <w:tr>
                <w:tc><w:p><w:r><w:t>R2C1</w:t></w:r><w:r><w:br w:type="page"/></w:r><w:r><w:t>R2C1b</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>R2C2</w:t></w:r></w:p></w:tc>
            </w:tr>
        </w:tbl>
    </w:body>
</w:document>"#,
    );

    write_entry(
        &mut writer,
        "word/_rels/document.xml.rels",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>"#,
    );

    writer.finish().unwrap();
}

fn build_reference_docx(path: &std::path::Path) {
    let file = std::fs::File::create(path).unwrap();
    let mut writer = zip::ZipWriter::new(file);

    write_entry(
        &mut writer,
        "[Content_Types].xml",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"#,
    );

    write_entry(
        &mut writer,
        "_rels/.rels",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"#,
    );

    write_entry(
        &mut writer,
        "word/document.xml",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r><w:t>参考文献</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>董蔼莹. 基于VR技术的园区全景漫游系统设计与实现[D]. 广东:华南农业大学,2019.</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>刘乾坤. 基于多张全景图的虚拟视点合成系统[D]. 天津:天津大学,2017.</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>作者简介</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>姓名：李良循；性别：女；出生年月：2000年9月</w:t></w:r>
        </w:p>
    </w:body>
</w:document>"#,
    );

    write_entry(
        &mut writer,
        "word/_rels/document.xml.rels",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>"#,
    );

    writer.finish().unwrap();
}

fn build_reference_docx_with_heading_terminator(path: &std::path::Path) {
    let file = std::fs::File::create(path).unwrap();
    let mut writer = zip::ZipWriter::new(file);

    write_entry(
        &mut writer,
        "[Content_Types].xml",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"#,
    );

    write_entry(
        &mut writer,
        "_rels/.rels",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"#,
    );

    write_entry(
        &mut writer,
        "word/document.xml",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r><w:t>参考文献</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>董蔼莹. 基于VR技术的园区全景漫游系统设计与实现[D]. 广东:华南农业大学,2019.</w:t></w:r>
        </w:p>
        <w:p>
            <w:r><w:t>刘乾坤. 基于多张全景图的虚拟视点合成系统[D]. 天津:天津大学,2017.</w:t></w:r>
        </w:p>
        <w:p>
            <w:pPr>
                <w:pStyle w:val="Heading1"/>
            </w:pPr>
            <w:r>
                <w:rPr>
                    <w:b/>
                    <w:sz w:val="28"/>
                </w:rPr>
                <w:t>第二章 结论</w:t>
            </w:r>
        </w:p>
        <w:p>
            <w:r><w:t>这个段落不应被当成参考文献</w:t></w:r>
        </w:p>
    </w:body>
</w:document>"#,
    );

    write_entry(
        &mut writer,
        "word/_rels/document.xml.rels",
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>"#,
    );

    writer.finish().unwrap();
}

#[tokio::test]
async fn test_health_endpoint() {
    let app = paper_audit_rust::create_app();
    let req = Request::builder()
        .method("GET")
        .uri("/health")
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(v.get("status").and_then(|s| s.as_str()).unwrap(), "healthy");
}

#[tokio::test]
async fn test_parse_and_annotate_flow() {
    use std::fs;
    use tempfile::tempdir;

    let dir = tempdir().unwrap();
    let file_path = dir.path().join("doc.docx");
    build_minimal_docx(&file_path);
    let file_path_str = file_path.to_string_lossy().to_string();

    let app = paper_audit_rust::create_app();

    // POST /parse
    let body = json!({"file_path": file_path_str}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/parse")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert!(v.get("sections").is_some());

    // POST /annotate
    let body = json!({"original_path": file_path_str, "issues": []}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/annotate")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert!(v.get("output_path").is_some());

    // verify output file exists
    let out = v.get("output_path").and_then(|p| p.as_str()).unwrap();
    assert!(std::path::Path::new(out).exists());

    // cleanup
    let _ = fs::remove_file(out);
}

#[tokio::test]
async fn test_parse_exposes_page_and_table_positions() {
    use tempfile::tempdir;

    let dir = tempdir().unwrap();
    let file_path = dir.path().join("paged.docx");
    build_page_break_docx(&file_path);

    let app = paper_audit_rust::create_app();
    let body = json!({"file_path": file_path.to_string_lossy().to_string()}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/parse")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();

    let sections = v
        .get("sections")
        .and_then(|value| value.as_array())
        .unwrap();
    assert!(sections.iter().any(|section| {
        section
            .get("position")
            .and_then(|position| position.get("page_start"))
            .and_then(|value| value.as_u64())
            == Some(1)
    }));
    assert!(sections.iter().any(|section| {
        section
            .get("position")
            .and_then(|position| position.get("page_end"))
            .and_then(|value| value.as_u64())
            == Some(2)
    }));

    let table = sections
        .iter()
        .find(|section| section.get("is_table").and_then(|value| value.as_bool()) == Some(true))
        .unwrap();
    assert_eq!(
        table
            .get("table_meta")
            .and_then(|meta| meta.get("is_cross_page"))
            .and_then(|value| value.as_bool()),
        Some(true)
    );
    assert_eq!(
        table
            .get("table_row_positions")
            .and_then(|value| value.as_array())
            .map(|rows| rows.len()),
        Some(2)
    );
    assert_eq!(
        v.get("metadata")
            .and_then(|metadata| metadata.get("page_numbering_mode"))
            .and_then(|value| value.as_str()),
        Some("explicit_or_mixed")
    );
}

#[tokio::test]
async fn test_parse_extracts_references() {
    use tempfile::tempdir;

    let dir = tempdir().unwrap();
    let file_path = dir.path().join("references.docx");
    build_reference_docx(&file_path);

    let app = paper_audit_rust::create_app();
    let body = json!({"file_path": file_path.to_string_lossy().to_string()}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/parse")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();

    let references = v
        .get("references")
        .and_then(|value| value.as_array())
        .expect("references should be present");
    assert_eq!(references.len(), 2);
    assert_eq!(references[0].get("index").and_then(|value| value.as_u64()), Some(1));
    assert_eq!(references[0].get("ref_id").and_then(|value| value.as_str()), Some("[1]"));
    assert!(references[0]
        .get("raw_text")
        .and_then(|value| value.as_str())
        .unwrap()
        .contains("董蔼莹"));
    assert_eq!(references[1].get("index").and_then(|value| value.as_u64()), Some(2));
    assert_eq!(references[1].get("ref_id").and_then(|value| value.as_str()), Some("[2]"));
}

#[tokio::test]
async fn test_parse_stops_references_on_heading_format() {
    use tempfile::tempdir;

    let dir = tempdir().unwrap();
    let file_path = dir.path().join("references_heading.docx");
    build_reference_docx_with_heading_terminator(&file_path);

    let app = paper_audit_rust::create_app();
    let body = json!({"file_path": file_path.to_string_lossy().to_string()}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/parse")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();

    let references = v
        .get("references")
        .and_then(|value| value.as_array())
        .expect("references should be present");
    assert_eq!(references.len(), 2);
    assert_eq!(references[0].get("ref_id").and_then(|value| value.as_str()), Some("[1]"));
    assert_eq!(references[1].get("ref_id").and_then(|value| value.as_str()), Some("[2]"));
}
