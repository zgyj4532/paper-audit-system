use quick_xml::events::Event;
use quick_xml::Reader;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use super::types::{ParagraphInfo, RunInfo, SectionInfo, TableRowInfo, TextFormat};
use super::xml::attr_value;

mod handlers;
pub(crate) mod references;

use self::handlers::{
    advance_page_break, apply_paragraph_style, apply_run_style, begin_paragraph_section,
    begin_table_section, finish_paragraph_section, finish_table_section, flush_table_row,
    record_paragraph_image, set_paragraph_has_math,
};

pub(crate) fn temp_output_path(input_path: &Path) -> PathBuf {
    let base = std::env::var("RUST_TEMP_DIR").unwrap_or_else(|_| "./temp/rust_engine".to_string());
    let mut out_dir = PathBuf::from(base);
    out_dir.push("rust_parse");
    let _ = fs::create_dir_all(&out_dir);
    let stem = input_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("document");
    out_dir.push(format!("{}_parsed.json", stem));
    out_dir
}

pub(crate) fn extract_sections(
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
    let mut current_table_row_positions: Vec<TableRowInfo> = Vec::new();
    let mut current_paragraph_images: Vec<String> = Vec::new();
    let mut current_paragraph_has_math = false;
    let mut current_paragraph_style: Option<String> = None;
    let mut current_paragraph_format = defaults.clone();
    let mut current_page: usize = 1;
    let mut saw_explicit_page_break = false;
    let mut current_paragraph_index: usize = 0;
    let mut current_row_index: usize = 0;
    let mut current_paragraph_page_start: usize = 1;
    let mut current_paragraph_page_end: usize = 1;
    let mut current_paragraph_has_page_break = false;
    let mut current_table_page_start: usize = 1;
    let mut current_table_page_end: usize = 1;
    let mut current_row_page_start: usize = 1;
    let mut current_row_page_end: usize = 1;
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
                begin_table_section(
                    current_page,
                    &mut current_row_index,
                    &mut current_section,
                    &mut current_table_page_start,
                    &mut current_table_page_end,
                    &mut current_table_rows,
                    &mut current_table_row_positions,
                    &mut current_row_cells,
                    &mut current_cell_text,
                );
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"tbl" => {
                finish_table_section(
                    in_cell,
                    &mut current_cell_text,
                    &mut current_row_cells,
                    &mut current_row_index,
                    &mut current_table_rows,
                    &mut current_table_row_positions,
                    &mut current_table_page_start,
                    &mut current_table_page_end,
                    current_row_page_start,
                    current_row_page_end,
                    &mut current_section,
                    &mut sections,
                );
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
                current_row_index += 1;
                current_row_page_start = current_page;
                current_row_page_end = current_page;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"tr" => {
                flush_table_row(
                    in_table,
                    &mut current_row_cells,
                    &mut current_table_rows,
                    &mut current_table_row_positions,
                    current_row_index,
                    current_row_page_start,
                    current_row_page_end,
                    &mut current_table_page_start,
                    &mut current_table_page_end,
                );
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
                begin_paragraph_section(
                    current_page,
                    defaults,
                    &mut current_paragraph_index,
                    &mut current_section,
                    &mut current_para,
                    &mut current_paragraph_images,
                    &mut current_paragraph_has_math,
                    &mut current_paragraph_style,
                    &mut current_paragraph_format,
                    &mut current_paragraph_page_start,
                    &mut current_paragraph_page_end,
                    &mut current_paragraph_has_page_break,
                );
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"p" => {
                finish_paragraph_section(
                    &mut current_para,
                    &current_paragraph_format,
                    current_paragraph_has_math,
                    &current_paragraph_images,
                    &current_paragraph_style,
                    current_paragraph_page_start,
                    current_paragraph_page_end,
                    &mut current_cell_text,
                    &mut current_section,
                    &mut sections,
                );
                in_para = false;
            }
            Ok(Event::Start(e)) if in_para && e.local_name().as_ref() == b"pPr" => {
                in_para_props = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"pPr" => {
                in_para_props = false;
                in_para_run_pr = false;
            }
            Ok(Event::Start(e))
                if in_para_props && e.local_name().as_ref() == b"pageBreakBefore" =>
            {
                if current_paragraph_page_start == current_page && !current_paragraph_has_page_break
                {
                    advance_page_break(
                        &mut current_page,
                        &mut saw_explicit_page_break,
                        &mut current_paragraph_page_end,
                        &mut current_row_page_end,
                        &mut current_table_page_end,
                    );
                    current_paragraph_page_start = current_page;
                }
            }
            Ok(Event::Start(e)) if in_para_props && e.local_name().as_ref() == b"rPr" => {
                in_para_run_pr = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"rPr" => {
                in_para_run_pr = false;
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_para_props && e.local_name().as_ref() == b"pStyle" =>
            {
                apply_paragraph_style(
                    &mut current_paragraph_format,
                    &mut current_paragraph_style,
                    styles,
                    &e,
                );
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_para_run_pr && e.local_name().as_ref() == b"rFonts" =>
            {
                current_paragraph_format.font = attr_value(&e, b"eastAsia")
                    .or_else(|| attr_value(&e, b"ascii"))
                    .or_else(|| attr_value(&e, b"hAnsi"))
                    .or_else(|| current_paragraph_format.font.clone());
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_para_run_pr
                    && (e.local_name().as_ref() == b"sz" || e.local_name().as_ref() == b"szCs") =>
            {
                current_paragraph_format.size_pt =
                    attr_value(&e, b"val").and_then(|v| super::format::parse_size_pt(&v));
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_para_run_pr && e.local_name().as_ref() == b"b" =>
            {
                current_paragraph_format.bold = Some(true);
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_para_run_pr && e.local_name().as_ref() == b"color" =>
            {
                current_paragraph_format.color = attr_value(&e, b"val");
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_para_run_pr && e.local_name().as_ref() == b"rStyle" =>
            {
                apply_run_style(&mut current_run.format, &e, styles);
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
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if (e.local_name().as_ref() == b"oMath")
                    || (e.local_name().as_ref() == b"oMathPara") =>
            {
                set_paragraph_has_math(&mut current_paragraph_has_math);
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if e.local_name().as_ref() == b"blip"
                    || e.local_name().as_ref() == b"imagedata" =>
            {
                record_paragraph_image(&e, image_targets, &mut current_paragraph_images);
            }
            Ok(Event::Start(e)) if in_run && e.local_name().as_ref() == b"rPr" => {
                in_run_pr = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"rPr" => {
                in_run_pr = false;
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_run_pr && e.local_name().as_ref() == b"rFonts" =>
            {
                current_run.format.font = attr_value(&e, b"eastAsia")
                    .or_else(|| attr_value(&e, b"ascii"))
                    .or_else(|| attr_value(&e, b"hAnsi"))
                    .or_else(|| current_run.format.font.clone());
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_run_pr
                    && (e.local_name().as_ref() == b"sz" || e.local_name().as_ref() == b"szCs") =>
            {
                current_run.format.size_pt =
                    attr_value(&e, b"val").and_then(|v| super::format::parse_size_pt(&v));
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_run_pr && e.local_name().as_ref() == b"b" =>
            {
                current_run.format.bold = Some(true);
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_run_pr && e.local_name().as_ref() == b"color" =>
            {
                current_run.format.color = attr_value(&e, b"val");
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_run_pr && e.local_name().as_ref() == b"rStyle" =>
            {
                apply_run_style(&mut current_run.format, &e, styles);
            }
            Ok(Event::Start(e)) if in_run && e.local_name().as_ref() == b"t" => {
                in_text = true;
            }
            Ok(Event::End(e)) if e.local_name().as_ref() == b"t" => {
                in_text = false;
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_run && e.local_name().as_ref() == b"br" =>
            {
                let break_type = attr_value(&e, b"type").unwrap_or_default();
                if break_type == "page" {
                    current_paragraph_has_page_break = true;
                    advance_page_break(
                        &mut current_page,
                        &mut saw_explicit_page_break,
                        &mut current_paragraph_page_end,
                        &mut current_row_page_end,
                        &mut current_table_page_end,
                    );
                }
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_run && e.local_name().as_ref() == b"lastRenderedPageBreak" =>
            {
                current_paragraph_has_page_break = true;
                advance_page_break(
                    &mut current_page,
                    &mut saw_explicit_page_break,
                    &mut current_paragraph_page_end,
                    &mut current_row_page_end,
                    &mut current_table_page_end,
                );
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
