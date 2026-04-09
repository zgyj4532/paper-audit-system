use serde_json::json;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

use super::document::{build_response, extract_sections};
use super::types::{ParseOptions, TextFormat};
use super::xml::{read_docx_member, read_relationships, read_styles};

pub fn parse_document(path: &str, options: &ParseOptions) -> serde_json::Value {
    let input_path = Path::new(path);
    let canonical_input = if input_path.is_absolute() {
        input_path.to_path_buf()
    } else {
        std::env::current_dir()
            .map(|cwd| cwd.join(input_path))
            .unwrap_or_else(|_| input_path.to_path_buf())
    };

    if !canonical_input.exists() {
        return json!({"success": false, "error": "file not found", "path": path});
    }

    let (defaults, styles): (TextFormat, HashMap<String, TextFormat>) = if canonical_input
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|s| s.eq_ignore_ascii_case("docx"))
        .unwrap_or(false)
    {
        read_styles(&canonical_input)
    } else {
        (TextFormat::default(), HashMap::new())
    };

    let image_targets = read_relationships(&canonical_input);

    let sections = match canonical_input
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|s| s.to_lowercase())
    {
        Some(ext) if ext == "docx" => match read_docx_member(&canonical_input, "word/document.xml")
        {
            Ok(xml) => extract_sections(&xml, &defaults, &styles, &image_targets),
            Err(err) => return json!({"success": false, "error": err, "path": path}),
        },
        _ => match fs::read_to_string(&canonical_input) {
            Ok(content) => content
                .lines()
                .map(|line| super::types::SectionInfo {
                    element_type: "Paragraph".to_string(),
                    text: line.trim().to_string(),
                    runs: vec![super::types::RunInfo {
                        text: line.trim().to_string(),
                        format: defaults.clone(),
                    }],
                    format: defaults.clone(),
                    ..super::types::SectionInfo::default()
                })
                .filter(|paragraph| !paragraph.text.is_empty())
                .collect(),
            Err(err) => {
                return json!({"success": false, "error": format!("failed to read file: {}", err), "path": path})
            }
        },
    };

    build_response(&canonical_input, sections, &defaults, options)
}
