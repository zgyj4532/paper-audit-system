use std::fs::{self, File};
use std::io::{Read, Write};
use tempfile::tempdir;
use zip::write::SimpleFileOptions;

fn write_entry(writer: &mut zip::ZipWriter<File>, name: &str, content: &str) {
    writer
        .start_file(name, SimpleFileOptions::default())
        .unwrap();
    writer.write_all(content.as_bytes()).unwrap();
}

fn build_minimal_docx(path: &std::path::Path) {
    let file = File::create(path).unwrap();
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
async fn test_annotator_adds_comments_package_parts() {
    let dir = tempdir().unwrap();
    let input = dir.path().join("input.docx");
    build_minimal_docx(&input);

    let issues = serde_json::json!([
        {
            "xml_path": "/w:body/w:p[1]",
            "raw_text": "Hello world"
        }
    ]);

    let result = paper_audit_rust::annotator::annotate_document(
        input.to_str().unwrap(),
        &issues,
        Some("annotated.docx"),
    )
    .unwrap();

    let output_path = result["output_path"].as_str().unwrap();
    let output_file = File::open(output_path).unwrap();
    let mut archive = zip::ZipArchive::new(output_file).unwrap();

    let mut comments_xml = String::new();
    archive
        .by_name("word/comments.xml")
        .unwrap()
        .read_to_string(&mut comments_xml)
        .unwrap();
    assert!(comments_xml.contains("paper-audit"));
    assert!(comments_xml.contains("Hello world"));

    let mut rels_xml = String::new();
    archive
        .by_name("word/_rels/document.xml.rels")
        .unwrap()
        .read_to_string(&mut rels_xml)
        .unwrap();
    assert!(rels_xml.contains("Target=\"comments.xml\""));

    let mut content_types_xml = String::new();
    archive
        .by_name("[Content_Types].xml")
        .unwrap()
        .read_to_string(&mut content_types_xml)
        .unwrap();
    assert!(content_types_xml.contains("/word/comments.xml"));

    let mut document_xml = String::new();
    archive
        .by_name("word/document.xml")
        .unwrap()
        .read_to_string(&mut document_xml)
        .unwrap();
    assert!(document_xml.contains("commentRangeStart"));
    assert!(document_xml.contains("commentRangeEnd"));
    assert!(document_xml.contains("commentReference"));

    let _ = fs::remove_file(output_path);
}