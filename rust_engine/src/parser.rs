use quick_xml::events::{BytesStart, Event};
use quick_xml::Reader;
use serde::Deserialize;
use serde_json::json;
use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use zip::ZipArchive;

#[derive(Default, Deserialize)]
pub struct ParseOptions {
    pub extract_styles: bool,
    pub compute_coordinates: bool,
    pub extract_images: bool,
}

#[derive(Default, Clone)]
struct TextFormat {
    font: Option<String>,
    size_pt: Option<String>,
    bold: Option<bool>,
    color: Option<String>,
    style: Option<String>,
}

#[derive(Default, Clone)]
struct StyleInfo {
    parent: Option<String>,
    format: TextFormat,
}

#[derive(Default, Clone)]
struct RunInfo {
    text: String,
    format: TextFormat,
}

#[derive(Default, Clone)]
struct ParagraphInfo {
    text: String,
    runs: Vec<RunInfo>,
    format: TextFormat,
}

#[derive(Default, Clone)]
struct SectionInfo {
    element_type: String,
    text: String,
    runs: Vec<RunInfo>,
    format: TextFormat,
    table_rows: Vec<Vec<String>>,
    images: Vec<String>,
    has_math: bool,
    paragraph_style: Option<String>,
}

fn temp_output_path(input_path: &Path) -> PathBuf {
    let base = std::env::var("RUST_TEMP_DIR").unwrap_or_else(|_| "./temp/rust_engine".to_string());
    let mut out_dir = PathBuf::from(base);
    out_dir.push("rust_parse");
    let _ = fs::create_dir_all(&out_dir);
    let stem = input_path.file_stem().and_then(|s| s.to_str()).unwrap_or("document");
    out_dir.push(format!("{}_parsed.json", stem));
    out_dir
}

fn read_docx_member(path: &Path, member_name: &str) -> Result<String, String> {
    let file = fs::File::open(path).map_err(|e| format!("failed to open file: {}", e))?;
    let mut archive = ZipArchive::new(file).map_err(|e| format!("failed to open docx archive: {}", e))?;
    let mut member = archive
        .by_name(member_name)
        .map_err(|e| format!("failed to read {}: {}", member_name, e))?;
    let mut xml = String::new();
    member
        .read_to_string(&mut xml)
        .map_err(|e| format!("failed to load {}: {}", member_name, e))?;
    Ok(xml)
}

fn attr_value(start: &BytesStart<'_>, key: &[u8]) -> Option<String> {
    start
        .attributes()
        .flatten()
        .find(|attr| {
            let name = attr.key.as_ref();
            name == key || name.rsplit(|b| *b == b':').next() == Some(key)
        })
        .and_then(|attr| String::from_utf8(attr.value.into_owned()).ok())
}

fn parse_size_pt(val: &str) -> Option<String> {
    val.parse::<f64>()
        .ok()
        .map(|half_points| half_points / 2.0)
        .map(|points| {
            if (points.fract()).abs() < f64::EPSILON {
                format!("{}pt", points as i64)
            } else {
                format!("{:.1}pt", points)
            }
        })
}

fn merge_format(base: &TextFormat, overlay: &TextFormat) -> TextFormat {
    TextFormat {
        font: overlay.font.clone().or_else(|| base.font.clone()),
        size_pt: overlay.size_pt.clone().or_else(|| base.size_pt.clone()),
        bold: overlay.bold.or(base.bold),
        color: overlay.color.clone().or_else(|| base.color.clone()),
        style: overlay.style.clone().or_else(|| base.style.clone()),
    }
}

fn read_relationships(path: &Path) -> HashMap<String, String> {
    let Ok(xml) = read_docx_member(path, "word/_rels/document.xml.rels") else {
        return HashMap::new();
    };

    let mut reader = Reader::from_str(&xml);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut relationships = HashMap::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if e.local_name().as_ref() == b"Relationship" => {
                let id = attr_value(&e, b"Id");
                let target = attr_value(&e, b"Target");
                if let (Some(id), Some(target)) = (id, target) {
                    relationships.insert(id, target);
                }
            }
            Ok(Event::Eof) => break,
            Ok(_) => {}
            Err(_) => break,
        }
        buf.clear();
    }

    relationships
}

fn read_styles(path: &Path) -> (TextFormat, HashMap<String, TextFormat>) {
    let Ok(xml) = read_docx_member(path, "word/styles.xml") else {
        return (TextFormat::default(), HashMap::new());
    };

    let mut reader = Reader::from_str(&xml);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut defaults = TextFormat::default();
    let mut raw_styles: HashMap<String, StyleInfo> = HashMap::new();
    let mut resolved_styles: HashMap<String, TextFormat> = HashMap::new();
    let mut in_doc_defaults = false;
    let mut in_style = false;
    let mut current_style_id: Option<String> = None;
    let mut current_style_parent: Option<String> = None;
    let mut current_style_format = TextFormat::default();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) if e.local_name().as_ref() == b"docDefaults" => {
                in_doc_defaults = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"docDefaults" => {
                in_doc_defaults = false;
            }
            Ok(Event::Start(e)) if e.local_name().as_ref() == b"style" => {
                in_style = true;
                current_style_id = attr_value(&e, b"styleId");
                current_style_parent = None;
                current_style_format = TextFormat::default();
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"style" => {
                if let Some(style_id) = current_style_id.take() {
                    raw_styles.insert(
                        style_id,
                        StyleInfo {
                            parent: current_style_parent.take(),
                            format: current_style_format.clone(),
                        },
                    );
                }
                in_style = false;
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_doc_defaults && e.local_name().as_ref() == b"rFonts" => {
                if defaults.font.is_none() {
                    defaults.font = attr_value(&e, b"eastAsia")
                        .or_else(|| attr_value(&e, b"ascii"))
                        .or_else(|| attr_value(&e, b"hAnsi"));
                }
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_doc_defaults && (e.local_name().as_ref() == b"sz" || e.local_name().as_ref() == b"szCs") => {
                if defaults.size_pt.is_none() {
                    defaults.size_pt = attr_value(&e, b"val").and_then(|v| parse_size_pt(&v));
                }
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_style && e.local_name().as_ref() == b"basedOn" => {
                current_style_parent = attr_value(&e, b"val");
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_style && e.local_name().as_ref() == b"rFonts" => {
                current_style_format.font = attr_value(&e, b"eastAsia")
                    .or_else(|| attr_value(&e, b"ascii"))
                    .or_else(|| attr_value(&e, b"hAnsi"))
                    .or_else(|| current_style_format.font.clone());
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_style && (e.local_name().as_ref() == b"sz" || e.local_name().as_ref() == b"szCs") => {
                current_style_format.size_pt = attr_value(&e, b"val").and_then(|v| parse_size_pt(&v));
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_style && e.local_name().as_ref() == b"b" => {
                current_style_format.bold = Some(true);
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_style && e.local_name().as_ref() == b"color" => {
                current_style_format.color = attr_value(&e, b"val");
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_style && e.local_name().as_ref() == b"rStyle" => {
                current_style_format.style = attr_value(&e, b"val");
            }
            Ok(Event::Eof) => break,
            Ok(_) => {}
            Err(_) => break,
        }
        buf.clear();
    }

    fn resolve_style(
        style_id: &str,
        raw_styles: &HashMap<String, StyleInfo>,
        resolved_styles: &mut HashMap<String, TextFormat>,
    ) -> Option<TextFormat> {
        if let Some(existing) = resolved_styles.get(style_id) {
            return Some(existing.clone());
        }

        let style = raw_styles.get(style_id)?;
        let resolved_base = style
            .parent
            .as_deref()
            .and_then(|parent| resolve_style(parent, raw_styles, resolved_styles))
            .unwrap_or_default();
        let merged = merge_format(&resolved_base, &style.format);
        resolved_styles.insert(style_id.to_string(), merged.clone());
        Some(merged)
    }

    let style_ids: Vec<String> = raw_styles.keys().cloned().collect();
    for style_id in style_ids {
        let _ = resolve_style(&style_id, &raw_styles, &mut resolved_styles);
    }

    (defaults, resolved_styles)
}

fn extract_sections(
    xml: &str,
    defaults: &TextFormat,
    styles: &HashMap<String, TextFormat>,
    image_targets: &HashMap<String, String>,
) -> Vec<SectionInfo> {
    let mut reader = Reader::from_str(xml);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut sections = Vec::new();
    let mut current_section: Option<SectionInfo> = None;
    let mut current_para = ParagraphInfo::default();
    let mut current_run = RunInfo::default();
    let mut current_cell_text = String::new();
    let mut current_row_cells: Vec<String> = Vec::new();
    let mut current_table_rows: Vec<Vec<String>> = Vec::new();
    let mut current_paragraph_images: Vec<String> = Vec::new();
    let mut current_paragraph_has_math = false;
    let mut current_paragraph_style: Option<String> = None;
    let mut current_paragraph_format = defaults.clone();
    let mut in_para = false;
    let mut in_run = false;
    let mut in_text = false;
    let mut in_run_pr = false;
    let mut in_para_run_pr = false;
    let mut in_table = false;
    let mut in_cell = false;
    let mut in_para_props = false;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) if e.local_name().as_ref() == b"tbl" => {
                in_table = true;
                current_section = Some(SectionInfo {
                    element_type: "Table".to_string(),
                    ..SectionInfo::default()
                });
                current_table_rows = Vec::new();
                current_row_cells = Vec::new();
                current_cell_text = String::new();
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"tbl" => {
                if let Some(mut section) = current_section.take() {
                    if section.element_type == "Table" {
                        if in_cell && !current_cell_text.trim().is_empty() {
                            current_row_cells.push(current_cell_text.trim().to_string());
                        }
                        if !current_row_cells.is_empty() {
                            current_table_rows.push(current_row_cells.clone());
                            current_row_cells.clear();
                        }
                        section.table_rows = current_table_rows.clone();
                        section.text = current_table_rows
                            .iter()
                            .map(|row| row.join("\t"))
                            .collect::<Vec<_>>()
                            .join("\n");
                        sections.push(section);
                    }
                }
                in_table = false;
                in_cell = false;
                in_para = false;
                in_run = false;
                in_text = false;
                in_run_pr = false;
                in_para_run_pr = false;
                in_para_props = false;
                current_paragraph_images.clear();
                current_paragraph_has_math = false;
                current_paragraph_style = None;
                current_paragraph_format = defaults.clone();
            }
            Ok(Event::Start(e)) if e.local_name().as_ref() == b"tr" => {
                current_row_cells = Vec::new();
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"tr" => {
                if in_table && !current_row_cells.is_empty() {
                    current_table_rows.push(current_row_cells.clone());
                    current_row_cells.clear();
                }
            }
            Ok(Event::Start(e)) if e.local_name().as_ref() == b"tc" => {
                in_cell = true;
                current_cell_text.clear();
                current_paragraph_images.clear();
                current_paragraph_has_math = false;
                current_paragraph_style = None;
                current_paragraph_format = defaults.clone();
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"tc" => {
                if in_table {
                    current_row_cells.push(current_cell_text.trim().to_string());
                }
                in_cell = false;
            }
            Ok(Event::Start(e)) if e.local_name().as_ref() == b"p" => {
                in_para = true;
                current_para = ParagraphInfo::default();
                current_paragraph_images.clear();
                current_paragraph_has_math = false;
                current_paragraph_style = None;
                current_paragraph_format = defaults.clone();
                if current_section.is_none() {
                    current_section = Some(SectionInfo {
                        element_type: "Paragraph".to_string(),
                        ..SectionInfo::default()
                    });
                }
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"p" => {
                if !current_para.runs.is_empty() {
                    current_para.text = current_para
                        .runs
                        .iter()
                        .map(|run| run.text.as_str())
                        .collect::<Vec<_>>()
                        .join("");
                    current_para.format = current_para
                        .runs
                        .first()
                        .map(|run| run.format.clone())
                        .unwrap_or_else(|| current_paragraph_format.clone());
                    if let Some(section) = current_section.as_mut() {
                        if section.element_type == "Paragraph" {
                            section.text = current_para.text.clone();
                            section.runs = current_para.runs.clone();
                            section.format = current_para.format.clone();
                            section.has_math = current_paragraph_has_math;
                            section.images = current_paragraph_images.clone();
                            section.paragraph_style = current_paragraph_style.clone();
                            sections.push(section.clone());
                            current_section = None;
                        } else if section.element_type == "Table" {
                            if !current_para.text.trim().is_empty() {
                                if !current_cell_text.is_empty() {
                                    current_cell_text.push(' ');
                                }
                                current_cell_text.push_str(current_para.text.trim());
                            }
                        }
                    }
                }
                in_para = false;
            }
            Ok(Event::Start(e)) if in_para && e.local_name().as_ref() == b"pPr" => {
                in_para_props = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"pPr" => {
                in_para_props = false;
                in_para_run_pr = false;
            }
            Ok(Event::Start(e)) if in_para_props && e.local_name().as_ref() == b"rPr" => {
                in_para_run_pr = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"rPr" => {
                in_para_run_pr = false;
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_para_props && e.local_name().as_ref() == b"pStyle" => {
                current_paragraph_style = attr_value(&e, b"val");
                if let Some(style_id) = current_paragraph_style.as_deref() {
                    if let Some(style_format) = styles.get(style_id) {
                        current_paragraph_format = merge_format(&current_paragraph_format, style_format);
                    }
                }
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_para_run_pr && e.local_name().as_ref() == b"rFonts" => {
                current_paragraph_format.font = attr_value(&e, b"eastAsia")
                    .or_else(|| attr_value(&e, b"ascii"))
                    .or_else(|| attr_value(&e, b"hAnsi"))
                    .or_else(|| current_paragraph_format.font.clone());
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_para_run_pr && (e.local_name().as_ref() == b"sz" || e.local_name().as_ref() == b"szCs") => {
                current_paragraph_format.size_pt = attr_value(&e, b"val").and_then(|v| parse_size_pt(&v));
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_para_run_pr && e.local_name().as_ref() == b"b" => {
                current_paragraph_format.bold = Some(true);
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_para_run_pr && e.local_name().as_ref() == b"color" => {
                current_paragraph_format.color = attr_value(&e, b"val");
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_para_run_pr && e.local_name().as_ref() == b"rStyle" => {
                current_paragraph_format.style = attr_value(&e, b"val");
                if let Some(style_id) = current_paragraph_format.style.as_deref() {
                    if let Some(style_format) = styles.get(style_id) {
                        current_paragraph_format = merge_format(&current_paragraph_format, style_format);
                    }
                }
            }
            Ok(Event::Start(e)) if in_para && e.local_name().as_ref() == b"r" => {
                in_run = true;
                current_run = RunInfo {
                    text: String::new(),
                    format: current_paragraph_format.clone(),
                };
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"r" => {
                if in_run && !current_run.text.trim().is_empty() {
                    if current_run.format.font.is_none() {
                        current_run.format.font = defaults.font.clone();
                    }
                    if current_run.format.size_pt.is_none() {
                        current_run.format.size_pt = defaults.size_pt.clone();
                    }
                    current_para.runs.push(current_run.clone());
                }
                in_run = false;
                in_text = false;
                in_run_pr = false;
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if (e.local_name().as_ref() == b"oMath") || (e.local_name().as_ref() == b"oMathPara") => {
                current_paragraph_has_math = true;
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if e.local_name().as_ref() == b"blip" || e.local_name().as_ref() == b"imagedata" => {
                let embed = attr_value(&e, b"embed").or_else(|| attr_value(&e, b"id"));
                if let Some(embed) = embed {
                    let target = image_targets.get(&embed).cloned().unwrap_or(embed.clone());
                    current_paragraph_images.push(target);
                }
            }
            Ok(Event::Start(e)) if in_run && e.local_name().as_ref() == b"rPr" => {
                in_run_pr = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"rPr" => {
                in_run_pr = false;
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_run_pr && e.local_name().as_ref() == b"rFonts" => {
                current_run.format.font = attr_value(&e, b"eastAsia")
                    .or_else(|| attr_value(&e, b"ascii"))
                    .or_else(|| attr_value(&e, b"hAnsi"))
                    .or_else(|| current_run.format.font.clone());
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_run_pr && (e.local_name().as_ref() == b"sz" || e.local_name().as_ref() == b"szCs") => {
                current_run.format.size_pt = attr_value(&e, b"val").and_then(|v| parse_size_pt(&v));
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_run_pr && e.local_name().as_ref() == b"b" => {
                current_run.format.bold = Some(true);
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_run_pr && e.local_name().as_ref() == b"color" => {
                current_run.format.color = attr_value(&e, b"val");
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e)) if in_run_pr && e.local_name().as_ref() == b"rStyle" => {
                current_run.format.style = attr_value(&e, b"val");
                if let Some(style_id) = current_run.format.style.as_deref() {
                    if let Some(style_format) = styles.get(style_id) {
                        current_run.format = merge_format(&current_run.format, style_format);
                    }
                }
            }
            Ok(Event::Start(e)) if in_run && e.local_name().as_ref() == b"t" => {
                in_text = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"t" => {
                in_text = false;
            }
            Ok(Event::Text(e)) if in_run && in_text => {
                if let Ok(text) = e.decode() {
                    current_run.text.push_str(&text);
                }
            }
            Ok(Event::CData(e)) if in_run && in_text => {
                if let Ok(text) = e.decode() {
                    current_run.text.push_str(&text);
                }
            }
            Ok(Event::Eof) => break,
            Ok(_) => {}
            Err(_) => break,
        }
        buf.clear();
    }

    if let Some(section) = current_section.take() {
        if section.element_type == "Paragraph" && !section.text.is_empty() {
            sections.push(section);
        }
    }

    sections
}

fn format_to_json(format: &TextFormat, fallback_alignment: &str) -> serde_json::Value {
    json!({
        "font": format.font.clone().unwrap_or_else(|| "unknown".to_string()),
        "size": format.size_pt.clone().unwrap_or_else(|| "unknown".to_string()),
        "bold": format.bold.unwrap_or(false),
        "alignment": fallback_alignment,
    })
}

fn build_response(
    input_path: &Path,
    sections_input: Vec<SectionInfo>,
    defaults: &TextFormat,
    options: &ParseOptions,
) -> serde_json::Value {
    let inferred_default_size = defaults.size_pt.clone().or_else(|| {
        sections_input.iter().find_map(|section| section.format.size_pt.clone())
    });
    let mut last_known_size: Option<String> = defaults.size_pt.clone();
    let mut last_known_size_by_page: HashMap<usize, String> = HashMap::new();

    let sections = sections_input
        .iter()
        .enumerate()
        .map(|(index, section)| {
            let page = (index / 20) + 1;
            let mut section_format = if section.format.font.is_none() && section.format.size_pt.is_none() {
                defaults.clone()
            } else {
                section.format.clone()
            };

            if section_format.size_pt.is_none() {
                if let Some(page_size) = last_known_size_by_page.get(&page) {
                    section_format.size_pt = Some(page_size.clone());
                } else if let Some(global_size) = last_known_size.clone() {
                    section_format.size_pt = Some(global_size);
                }
            }

            if let Some(size) = section_format.size_pt.clone() {
                last_known_size = Some(size.clone());
                last_known_size_by_page.insert(page, size);
            }

            let runs = section
                .runs
                .iter()
                .map(|run| {
                    json!({
                        "text": run.text,
                        "style": run.format.style.clone().unwrap_or_else(|| "Normal".to_string()),
                        "font": run.format.font.clone().or_else(|| defaults.font.clone()).unwrap_or_else(|| "unknown".to_string()),
                        "size": run.format.size_pt.clone().or_else(|| section_format.size_pt.clone()).or_else(|| defaults.size_pt.clone()).unwrap_or_else(|| "unknown".to_string()),
                        "color": run.format.color.clone().unwrap_or_else(|| "000000".to_string())
                    })
                })
                .collect::<Vec<_>>();
            let mut section_json = serde_json::Map::new();
            section_json.insert("id".to_string(), json!(index + 1));
            section_json.insert("element_type".to_string(), json!(section.element_type.clone()));
            section_json.insert("level".to_string(), json!(0));
            section_json.insert("raw_text".to_string(), json!(section.text.clone()));
            section_json.insert("xml_path".to_string(), json!(format!("/w:body/w:p[{}]", index + 1)));
            if options.extract_styles {
                section_json.insert("formatting".to_string(), format_to_json(&section_format, "left"));
                if let Some(style) = section.paragraph_style.as_ref() {
                    if let Some(formatting) = section_json.get_mut("formatting") {
                        if let Some(obj) = formatting.as_object_mut() {
                            obj.insert("paragraph_style".to_string(), json!(style));
                        }
                    }
                }
            }
            if options.compute_coordinates {
                section_json.insert(
                    "coordinates".to_string(),
                    json!({
                        "page": (index / 20) + 1,
                        "x": 0,
                        "y": (index as f64) * 24.0,
                        "width": 450,
                        "height": 20
                    }),
                );
            }
            section_json.insert("runs".to_string(), json!(runs));
            if !section.table_rows.is_empty() {
                section_json.insert("table_rows".to_string(), json!(section.table_rows.clone()));
            }
            if options.extract_images {
                section_json.insert("images".to_string(), json!(section.images.clone()));
            }
            if section.has_math {
                section_json.insert("has_math".to_string(), json!(true));
            }
            serde_json::Value::Object(section_json)
        })
        .collect::<Vec<_>>();

    let word_count = sections_input
        .iter()
        .flat_map(|p| p.text.split_whitespace())
        .count();

    let metadata = json!({
        "total_pages": std::cmp::max(1, (sections_input.len() + 19) / 20),
        "total_words": word_count,
        "has_math": sections_input.iter().any(|section| section.has_math),
        "total_paragraphs": sections_input.iter().filter(|section| section.element_type == "Paragraph").count(),
        "total_tables": sections_input.iter().filter(|section| section.element_type == "Table").count(),
    });

    let temp_output_path = temp_output_path(input_path);
    let mut data = serde_json::Map::new();
    data.insert("sections".to_string(), json!(sections));
    if options.extract_styles {
        data.insert(
            "styles".to_string(),
            json!({
                "default_run": {
                    "font": defaults.font.clone().unwrap_or_else(|| "unknown".to_string()),
                    "size": inferred_default_size.clone().unwrap_or_else(|| "unknown".to_string()),
                }
            }),
        );
    }
    data.insert("metadata".to_string(), metadata.clone());
    if options.extract_images {
        let images: Vec<String> = sections_input
            .iter()
            .flat_map(|section| section.images.clone())
            .collect();
        data.insert("images".to_string(), json!(images));
    }

    let payload = json!({
        "success": true,
        "data": data.clone(),
        "sections": sections,
        "styles": if options.extract_styles {
            json!({
                "default_run": {
                    "font": defaults.font.clone().unwrap_or_else(|| "unknown".to_string()),
                    "size": inferred_default_size.clone().unwrap_or_else(|| "unknown".to_string()),
                }
            })
        } else {
            serde_json::Value::Null
        },
        "metadata": metadata,
        "temp_output_path": temp_output_path,
    });

    let _ = fs::write(
        &temp_output_path,
        serde_json::to_string_pretty(&payload).unwrap_or_default(),
    );
    payload
}

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

    let (defaults, styles) = if canonical_input
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
        Some(ext) if ext == "docx" => match read_docx_member(&canonical_input, "word/document.xml") {
            Ok(xml) => extract_sections(&xml, &defaults, &styles, &image_targets),
            Err(err) => return json!({"success": false, "error": err, "path": path}),
        },
        _ => match fs::read_to_string(&canonical_input) {
            Ok(content) => content
                .lines()
                .map(|line| SectionInfo {
                    element_type: "Paragraph".to_string(),
                    text: line.trim().to_string(),
                    runs: vec![RunInfo {
                        text: line.trim().to_string(),
                        format: defaults.clone(),
                    }],
                    format: defaults.clone(),
                    ..SectionInfo::default()
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