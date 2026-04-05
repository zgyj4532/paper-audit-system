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
