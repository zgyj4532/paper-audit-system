use quick_xml::events::BytesStart;
use std::collections::HashMap;

use super::super::format::merge_format;
use super::super::types::{ParagraphInfo, SectionInfo, TableRowInfo, TextFormat};
use super::super::xml::attr_value;

pub(crate) fn advance_page_break(
    current_page: &mut usize,
    saw_explicit_page_break: &mut bool,
    current_paragraph_page_end: &mut usize,
    current_row_page_end: &mut usize,
    current_table_page_end: &mut usize,
) {
    *current_page += 1;
    *saw_explicit_page_break = true;
    *current_paragraph_page_end = *current_page;
    *current_row_page_end = *current_page;
    *current_table_page_end = *current_page;
}

pub(crate) fn begin_table_section(
    current_page: usize,
    current_row_index: &mut usize,
    current_section: &mut Option<SectionInfo>,
    current_table_page_start: &mut usize,
    current_table_page_end: &mut usize,
    current_table_rows: &mut Vec<Vec<String>>,
    current_table_row_positions: &mut Vec<TableRowInfo>,
    current_row_cells: &mut Vec<String>,
    current_cell_text: &mut String,
) {
    *current_table_page_start = current_page;
    *current_table_page_end = current_page;
    *current_row_index = 0;
    *current_section = Some(SectionInfo {
        element_type: "Table".to_string(),
        is_table: true,
        page_start: Some(current_page),
        page_end: Some(current_page),
        ..SectionInfo::default()
    });
    current_table_rows.clear();
    current_table_row_positions.clear();
    current_row_cells.clear();
    current_cell_text.clear();
}

pub(crate) fn flush_table_row(
    in_table: bool,
    current_row_cells: &mut Vec<String>,
    current_table_rows: &mut Vec<Vec<String>>,
    current_table_row_positions: &mut Vec<TableRowInfo>,
    current_row_index: usize,
    current_row_page_start: usize,
    current_row_page_end: usize,
    current_table_page_start: &mut usize,
    current_table_page_end: &mut usize,
) {
    if in_table && !current_row_cells.is_empty() {
        current_table_rows.push(current_row_cells.clone());
        current_table_row_positions.push(TableRowInfo {
            row_index: current_row_index,
            cells: current_row_cells.clone(),
            page_start: current_row_page_start,
            page_end: current_row_page_end,
        });
        *current_table_page_end = (*current_table_page_end).max(current_row_page_end);
        if current_row_page_end > current_row_page_start {
            *current_table_page_start = (*current_table_page_start).min(current_row_page_start);
        }
        current_row_cells.clear();
    }
}

pub(crate) fn finish_table_section(
    in_cell: bool,
    current_cell_text: &mut String,
    current_row_cells: &mut Vec<String>,
    current_row_index: &mut usize,
    current_table_rows: &mut Vec<Vec<String>>,
    current_table_row_positions: &mut Vec<TableRowInfo>,
    current_table_page_start: &mut usize,
    current_table_page_end: &mut usize,
    current_row_page_start: usize,
    current_row_page_end: usize,
    current_section: &mut Option<SectionInfo>,
    sections: &mut Vec<SectionInfo>,
) {
    if in_cell && !current_cell_text.trim().is_empty() {
        current_row_cells.push(current_cell_text.trim().to_string());
    }
    flush_table_row(
        true,
        current_row_cells,
        current_table_rows,
        current_table_row_positions,
        *current_row_index,
        current_row_page_start,
        current_row_page_end,
        current_table_page_start,
        current_table_page_end,
    );

    if let Some(mut section) = current_section.take() {
        if section.element_type == "Table" {
            section.table_rows = current_table_rows.clone();
            section.table_row_positions = current_table_row_positions.clone();
            section.text = current_table_rows
                .iter()
                .map(|row| row.join("\t"))
                .collect::<Vec<_>>()
                .join("\n");
            section.page_start = Some(*current_table_page_start);
            section.page_end = Some(*current_table_page_end);
            sections.push(section);
        }
    }
}

pub(crate) fn begin_paragraph_section(
    current_page: usize,
    defaults: &TextFormat,
    current_paragraph_index: &mut usize,
    current_section: &mut Option<SectionInfo>,
    current_para: &mut ParagraphInfo,
    current_paragraph_images: &mut Vec<String>,
    current_paragraph_has_math: &mut bool,
    current_paragraph_style: &mut Option<String>,
    current_paragraph_format: &mut TextFormat,
    current_paragraph_page_start: &mut usize,
    current_paragraph_page_end: &mut usize,
    current_paragraph_has_page_break: &mut bool,
) {
    *current_para = ParagraphInfo::default();
    current_paragraph_images.clear();
    *current_paragraph_has_math = false;
    *current_paragraph_style = None;
    *current_paragraph_format = defaults.clone();
    *current_paragraph_page_start = current_page;
    *current_paragraph_page_end = current_page;
    *current_paragraph_has_page_break = false;
    if current_section.is_none() {
        *current_paragraph_index += 1;
        *current_section = Some(SectionInfo {
            element_type: "Paragraph".to_string(),
            is_table: false,
            paragraph_index: Some(*current_paragraph_index),
            page_start: Some(current_page),
            page_end: Some(current_page),
            ..SectionInfo::default()
        });
    }
}

pub(crate) fn finish_paragraph_section(
    current_para: &mut ParagraphInfo,
    current_paragraph_format: &TextFormat,
    current_paragraph_has_math: bool,
    current_paragraph_images: &[String],
    current_paragraph_style: &Option<String>,
    current_paragraph_page_start: usize,
    current_paragraph_page_end: usize,
    current_cell_text: &mut String,
    current_section: &mut Option<SectionInfo>,
    sections: &mut Vec<SectionInfo>,
) {
    if current_para.runs.is_empty() {
        return;
    }

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
            section.images = current_paragraph_images.to_vec();
            section.paragraph_style = current_paragraph_style.clone();
            section.page_start = Some(current_paragraph_page_start);
            section.page_end = Some(current_paragraph_page_end);
            sections.push(section.clone());
            *current_section = None;
        } else if section.element_type == "Table" && !current_para.text.trim().is_empty() {
            if !current_cell_text.is_empty() {
                current_cell_text.push(' ');
            }
            current_cell_text.push_str(current_para.text.trim());
        }
    }
}

pub(crate) fn set_paragraph_has_math(current_paragraph_has_math: &mut bool) {
    *current_paragraph_has_math = true;
}

pub(crate) fn record_paragraph_image(
    event: &BytesStart,
    image_targets: &HashMap<String, String>,
    current_paragraph_images: &mut Vec<String>,
) {
    let embed = attr_value(event, b"embed").or_else(|| attr_value(event, b"id"));
    if let Some(embed) = embed {
        let target = image_targets.get(&embed).cloned().unwrap_or(embed);
        current_paragraph_images.push(target);
    }
}

pub(crate) fn apply_paragraph_style(
    current_paragraph_format: &mut TextFormat,
    current_paragraph_style: &mut Option<String>,
    styles: &HashMap<String, TextFormat>,
    event: &BytesStart,
) {
    *current_paragraph_style = attr_value(event, b"val");
    if let Some(style_id) = current_paragraph_style.as_deref() {
        if let Some(style_format) = styles.get(style_id) {
            *current_paragraph_format = merge_format(current_paragraph_format, style_format);
        }
    }
}

pub(crate) fn apply_run_style(
    current_run_format: &mut TextFormat,
    event: &BytesStart,
    styles: &HashMap<String, TextFormat>,
) {
    current_run_format.style = attr_value(event, b"val");
    if let Some(style_id) = current_run_format.style.as_deref() {
        if let Some(style_format) = styles.get(style_id) {
            *current_run_format = merge_format(current_run_format, style_format);
        }
    }
}
