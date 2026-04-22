use serde_json::json;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

use super::format::format_to_json;
use super::types::{ParseOptions, SectionInfo, TextFormat};

pub(crate) use super::sections::extract_sections;

pub(crate) fn build_response(
    input_path: &Path,
    sections_input: Vec<SectionInfo>,
    defaults: &TextFormat,
    options: &ParseOptions,
) -> serde_json::Value {
    let inferred_default_size = defaults.size_pt.clone().or_else(|| {
        sections_input
            .iter()
            .find_map(|section| section.format.size_pt.clone())
    });
    let mut last_known_size: Option<String> = defaults.size_pt.clone();
    let mut last_known_size_by_page: HashMap<usize, String> = HashMap::new();
    let has_explicit_page_positions = sections_input
        .iter()
        .any(|section| section.page_start.unwrap_or(1) > 1 || section.page_end.unwrap_or(1) > 1);
    let detected_pages = if has_explicit_page_positions {
        sections_input
            .iter()
            .filter_map(|section| section.page_end.or(section.page_start))
            .max()
            .unwrap_or(1)
    } else {
        std::cmp::max(1, (sections_input.len() + 19) / 20)
    };

    let sections = sections_input
        .iter()
        .enumerate()
        .map(|(index, section)| {
            let page = section.page_start.or(section.page_end).unwrap_or((index / 20) + 1);
            let page_end = section.page_end.or(section.page_start).unwrap_or(page);
            let paragraph_index = section.paragraph_index.unwrap_or(index + 1);
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
            section_json.insert("text".to_string(), json!(section.text.clone()));
            section_json.insert("raw_text".to_string(), json!(section.text.clone()));
            section_json.insert("xml_path".to_string(), json!(format!("/w:body/w:p[{}]", index + 1)));
            section_json.insert("is_table".to_string(), json!(section.is_table));
            section_json.insert(
                "position".to_string(),
                json!({
                    "paragraph_index": paragraph_index,
                    "page_start": page,
                    "page_end": page_end,
                    "xml_path": format!("/w:body/w:p[{}]", index + 1)
                }),
            );
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
                        "page": page,
                        "x": 0,
                        "y": (paragraph_index as f64) * 24.0,
                        "width": 450,
                        "height": 20
                    }),
                );
            }
            section_json.insert("runs".to_string(), json!(runs));
            if !section.table_rows.is_empty() {
                section_json.insert("table_rows".to_string(), json!(section.table_rows.clone()));
                section_json.insert(
                    "table_row_positions".to_string(),
                    json!(
                        section
                            .table_row_positions
                            .iter()
                            .map(|row| {
                                json!({
                                    "row_index": row.row_index,
                                    "cells": row.cells,
                                    "page_start": row.page_start,
                                    "page_end": row.page_end,
                                    "is_cross_page": row.page_end > row.page_start,
                                })
                            })
                            .collect::<Vec<_>>()
                    ),
                );
                section_json.insert(
                    "table_meta".to_string(),
                    json!({
                        "row_count": section.table_rows.len(),
                        "column_count": section.table_rows.iter().map(|row| row.len()).max().unwrap_or(0),
                        "page_start": page,
                        "page_end": page_end,
                        "is_cross_page": page_end > page,
                    }),
                );
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

    let references = super::sections::references::extract_references(&sections_input);

    let word_count = sections_input
        .iter()
        .flat_map(|p| p.text.split_whitespace())
        .count();

    let metadata = json!({
        "total_pages": detected_pages,
        "page_numbering_mode": if has_explicit_page_positions { "explicit_or_mixed" } else { "estimated" },
        "total_words": word_count,
        "has_math": sections_input.iter().any(|section| section.has_math),
        "total_paragraphs": sections_input.iter().filter(|section| section.element_type == "Paragraph").count(),
        "total_tables": sections_input.iter().filter(|section| section.element_type == "Table").count(),
    });

    let temp_output_path = super::sections::temp_output_path(input_path);
    let mut data = serde_json::Map::new();
    data.insert("sections".to_string(), json!(sections));
    data.insert("references".to_string(), json!(references.clone()));
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
        "temp_output_path": temp_output_path,
    });

    let _ = fs::write(
        &temp_output_path,
        serde_json::to_string_pretty(&payload).unwrap_or_default(),
    );
    payload
}
