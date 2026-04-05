use serde_json::Value;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use zip::write::SimpleFileOptions;

fn temp_output_dir() -> PathBuf {
    let base = std::env::var("RUST_TEMP_DIR").unwrap_or_else(|_| "./temp/rust_engine".to_string());
    let mut out_dir = PathBuf::from(base);
    out_dir.push("rust_output");
    let _ = fs::create_dir_all(&out_dir);
    out_dir
}

fn default_output_filename(original_path: &Path) -> String {
    let stem = original_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("document");
    format!("{}_annotated.docx", stem)
}

fn read_zip_xml(archive: &mut zip::ZipArchive<fs::File>, name: &str) -> Result<String, String> {
    let mut member = archive
        .by_name(name)
        .map_err(|e| format!("failed to read {}: {}", name, e))?;
    let mut xml = String::new();
    member
        .read_to_string(&mut xml)
        .map_err(|e| format!("failed to read {}: {}", name, e))?;
    Ok(xml)
}

fn insert_before_closing_tag(xml: &str, closing_tag: &str, snippet: &str) -> String {
    if let Some(index) = xml.rfind(closing_tag) {
        let mut updated = String::with_capacity(xml.len() + snippet.len());
        updated.push_str(&xml[..index]);
        updated.push_str(snippet);
        updated.push_str(&xml[index..]);
        return updated;
    }
    let mut updated = xml.to_string();
    updated.push_str(snippet);
    updated
}

fn next_relationship_id(xml: &str) -> String {
    let mut max_id = 0usize;
    let mut cursor = 0usize;
    while let Some(start) = xml[cursor..].find("Id=\"rId") {
        let start_index = cursor + start + 7;
        let mut end_index = start_index;
        while end_index < xml.len() {
            let byte = xml.as_bytes()[end_index];
            if !byte.is_ascii_digit() {
                break;
            }
            end_index += 1;
        }
        if end_index > start_index {
            if let Ok(value) = xml[start_index..end_index].parse::<usize>() {
                max_id = max_id.max(value);
            }
        }
        cursor = end_index.saturating_add(1);
    }
    format!("rId{}", max_id + 1)
}

fn ensure_comments_relationship(xml: &str) -> String {
    if xml.contains("Target=\"comments.xml\"") || xml.contains("Target=\"/word/comments.xml\"") {
        return xml.to_string();
    }

    let rel_id = next_relationship_id(xml);
    let relationship = format!(
        r#"<Relationship Id="{}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>"#,
        rel_id
    );
    insert_before_closing_tag(xml, "</Relationships>", &relationship)
}

fn ensure_comments_content_type(xml: &str) -> String {
    if xml.contains("/word/comments.xml") {
        return xml.to_string();
    }

    let override_entry = r#"<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>"#;
    insert_before_closing_tag(xml, "</Types>", override_entry)
}

pub fn annotate_document(
    original_path: &str,
    issues: &Value,
    output_filename: Option<&str>,
) -> Result<serde_json::Value, String> {
    let input = Path::new(original_path);
    if !input.exists() {
        return Err(format!("input file not found: {}", original_path));
    }

    let _issues_count = issues.as_array().map(|items| items.len()).unwrap_or(0);
    let out_dir = temp_output_dir();
    let filename = output_filename
        .filter(|name| !name.trim().is_empty())
        .map(|name| name.to_string())
        .unwrap_or_else(|| default_output_filename(input));
    let dest = out_dir.join(filename);

    // Create annotated docx by modifying document.xml and adding comments.xml
    let file = fs::File::open(input).map_err(|e| format!("failed to open input docx: {}", e))?;
    let mut archive =
        zip::ZipArchive::new(file).map_err(|e| format!("failed to open docx archive: {}", e))?;

    // Read original document.xml
    let mut doc_xml = read_zip_xml(&mut archive, "word/document.xml")?;
    let original_rels_xml = read_zip_xml(&mut archive, "word/_rels/document.xml.rels").unwrap_or_else(|_| {
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>"#.to_string()
    });
    let original_content_types_xml = read_zip_xml(&mut archive, "[Content_Types].xml").unwrap_or_else(|_| {
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>"#.to_string()
    });

    // Build comments XML and collect insertions for comment markers around paragraph-level xml_path if available
    let mut comments = Vec::new();
    // collect insertions to apply from back to front to avoid shifting indices
    let mut insertions: Vec<(usize, String)> = Vec::new();
    if let Some(array) = issues.as_array() {
        for (i, item) in array.iter().enumerate() {
            let id = (i + 1) as i32;
            let text = item
                .get("raw_text")
                .and_then(|v| v.as_str())
                .unwrap_or("注释");
            comments.push((id, text.to_string()));
            // Try to insert markers at paragraph level based on xml_path like /w:body/w:p[5]
            if let Some(xml_path) = item.get("xml_path").and_then(|v| v.as_str()) {
                if let Some(start_idx) = extract_paragraph_index(xml_path) {
                    // Find the nth occurrence of <w:p
                    let mut occ = 0usize;
                    let mut insert_pos_start = None;
                    let mut insert_pos_end = None;
                    for (pos, _) in doc_xml.match_indices("<w:p") {
                        occ += 1;
                        if occ == start_idx {
                            // place start marker before the first <w:r> inside this paragraph
                            if let Some(p_end) = doc_xml[pos..].find("</w:p>") {
                                // find position of first <w:r> inside paragraph
                                if let Some(r_pos) = doc_xml[pos..pos + p_end].find("<w:r") {
                                    insert_pos_start = Some(pos + r_pos);
                                }
                                // end marker before </w:p>
                                insert_pos_end = Some(pos + p_end);
                            }
                            break;
                        }
                    }
                    if let Some(spos) = insert_pos_start {
                        let start_marker = format!("<w:commentRangeStart w:id=\"{}\"/>", id);
                        insertions.push((spos, start_marker));
                    }
                    if let Some(epos) = insert_pos_end {
                        let end_marker = format!("<w:commentRangeEnd w:id=\"{}\"/>", id);
                        let ref_run = format!("<w:r><w:commentReference w:id=\"{}\"/></w:r>", id);
                        // insert end marker before </w:p>, and the reference run immediately after it
                        let end_marker_len = end_marker.len();
                        insertions.push((epos, end_marker));
                        insertions.push((epos + end_marker_len, ref_run));
                    }
                }
            }
        }
    }

    // Apply collected insertions from highest index to lowest to avoid shifting earlier offsets.
    if !insertions.is_empty() {
        // sort by position descending
        insertions.sort_by(|a, b| b.0.cmp(&a.0));
        let mut doc_len = doc_xml.len();
        for (mut pos, content) in insertions {
            // clamp position
            if pos > doc_len {
                pos = doc_len;
            }
            // move to next valid UTF-8 char boundary if needed
            while pos < doc_len && !doc_xml.is_char_boundary(pos) {
                pos += 1;
            }
            if pos > doc_len {
                pos = doc_len;
            }
            doc_xml.insert_str(pos, &content);
            // update doc_len since we've mutated the string
            doc_len = doc_xml.len();
        }
    }

    let comments_enabled = !comments.is_empty();
    let mut rels_xml = original_rels_xml;
    let mut content_types_xml = original_content_types_xml;
    if comments_enabled {
        rels_xml = ensure_comments_relationship(&rels_xml);
        content_types_xml = ensure_comments_content_type(&content_types_xml);
    }

    // Build comments.xml content
    let mut comments_xml = String::from(
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
"#,
    );
    for (id, text) in &comments {
        comments_xml.push_str(&format!(
            "  <w:comment w:id=\"{}\" w:author=\"paper-audit\">",
            id
        ));
        comments_xml.push_str(&format!(
            "<w:p><w:r><w:t>{}</w:t></w:r></w:p>",
            xml_escape(text)
        ));
        comments_xml.push_str("</w:comment>\n");
    }
    comments_xml.push_str("</w:comments>");

    // Create new zip with modified document.xml and comments.xml
    let out_file =
        fs::File::create(&dest).map_err(|e| format!("failed to create output file: {}", e))?;
    let mut writer = zip::ZipWriter::new(out_file);
    // use default FileOptions inline to avoid type-inference ambiguity

    // copy all original entries, replacing document.xml and adding comments.xml
    let mut has_document_rels = false;
    let mut has_content_types = false;
    for i in 0..archive.len() {
        let mut file = archive
            .by_index(i)
            .map_err(|e| format!("zip read error: {}", e))?;
        let name = file.name().to_string();
        // binary-safe read
        let mut buffer = Vec::new();
        file.read_to_end(&mut buffer)
            .map_err(|e| format!("failed reading entry: {}", e))?;
        if name == "word/document.xml" {
            writer
                .start_file(name, SimpleFileOptions::default())
                .map_err(|e| format!("zip write error: {}", e))?;
            writer
                .write_all(doc_xml.as_bytes())
                .map_err(|e| format!("failed to write document.xml: {}", e))?;
        } else if name == "word/_rels/document.xml.rels" {
            has_document_rels = true;
            writer
                .start_file(name, SimpleFileOptions::default())
                .map_err(|e| format!("zip write error: {}", e))?;
            writer
                .write_all(rels_xml.as_bytes())
                .map_err(|e| format!("failed to write document.xml.rels: {}", e))?;
        } else if name == "[Content_Types].xml" {
            has_content_types = true;
            writer
                .start_file(name, SimpleFileOptions::default())
                .map_err(|e| format!("zip write error: {}", e))?;
            writer
                .write_all(content_types_xml.as_bytes())
                .map_err(|e| format!("failed to write [Content_Types].xml: {}", e))?;
        } else {
            writer
                .start_file(name, SimpleFileOptions::default())
                .map_err(|e| format!("zip write error: {}", e))?;
            writer
                .write_all(&buffer)
                .map_err(|e| format!("failed to write entry: {}", e))?;
        }
    }

    if comments_enabled && !has_document_rels {
        writer
            .start_file("word/_rels/document.xml.rels", SimpleFileOptions::default())
            .map_err(|e| format!("zip write error: {}", e))?;
        writer
            .write_all(rels_xml.as_bytes())
            .map_err(|e| format!("failed to write document.xml.rels: {}", e))?;
    }

    if comments_enabled && !has_content_types {
        writer
            .start_file("[Content_Types].xml", SimpleFileOptions::default())
            .map_err(|e| format!("zip write error: {}", e))?;
        writer
            .write_all(content_types_xml.as_bytes())
            .map_err(|e| format!("failed to write [Content_Types].xml: {}", e))?;
    }

    // add comments.xml
    if comments_enabled {
        writer
            .start_file("word/comments.xml", SimpleFileOptions::default())
            .map_err(|e| format!("zip write error: {}", e))?;
        writer
            .write_all(comments_xml.as_bytes())
            .map_err(|e| format!("failed to write comments.xml: {}", e))?;
    }
    writer
        .finish()
        .map_err(|e| format!("failed to finish zip: {}", e))?;

    let file_size_kb = fs::metadata(&dest)
        .map_err(|e| format!("failed to stat output file: {}", e))?
        .len()
        / 1024;

    Ok(serde_json::json!({
        "success": true,
        "output_path": dest.to_string_lossy(),
        "stats": {
            "comments_injected": comments.len(),
            "file_size_kb": file_size_kb,
        }
    }))
}

fn extract_paragraph_index(xml_path: &str) -> Option<usize> {
    // extract number from pattern like /w:body/w:p[5]
    if let Some(start) = xml_path.rfind('[') {
        if let Some(end) = xml_path.rfind(']') {
            if end > start + 1 {
                let num = &xml_path[start + 1..end];
                return num.parse::<usize>().ok();
            }
        }
    }
    None
}

fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}
