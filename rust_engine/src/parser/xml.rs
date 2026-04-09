use quick_xml::events::{BytesStart, Event};
use quick_xml::Reader;
use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::Path;
use zip::ZipArchive;

use super::format::{merge_format, parse_size_pt};
use super::types::{StyleInfo, TextFormat};

pub(crate) fn read_docx_member(path: &Path, member_name: &str) -> Result<String, String> {
    let file = fs::File::open(path).map_err(|e| format!("failed to open file: {}", e))?;
    let mut archive =
        ZipArchive::new(file).map_err(|e| format!("failed to open docx archive: {}", e))?;
    let mut member = archive
        .by_name(member_name)
        .map_err(|e| format!("failed to read {}: {}", member_name, e))?;
    let mut xml = String::new();
    member
        .read_to_string(&mut xml)
        .map_err(|e| format!("failed to load {}: {}", member_name, e))?;
    Ok(xml)
}

pub(crate) fn attr_value(start: &BytesStart<'_>, key: &[u8]) -> Option<String> {
    start
        .attributes()
        .flatten()
        .find(|attr| {
            let name = attr.key.as_ref();
            name == key || name.rsplit(|b| *b == b':').next() == Some(key)
        })
        .and_then(|attr| String::from_utf8(attr.value.into_owned()).ok())
}

pub(crate) fn read_relationships(path: &Path) -> HashMap<String, String> {
    let Ok(xml) = read_docx_member(path, "word/_rels/document.xml.rels") else {
        return HashMap::new();
    };

    let mut reader = Reader::from_str(&xml);
    reader.config_mut().trim_text(true);
    let mut buf = Vec::new();
    let mut relationships = HashMap::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if e.local_name().as_ref() == b"Relationship" =>
            {
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

pub(crate) fn read_styles(path: &Path) -> (TextFormat, HashMap<String, TextFormat>) {
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
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_doc_defaults && e.local_name().as_ref() == b"rFonts" =>
            {
                if defaults.font.is_none() {
                    defaults.font = attr_value(&e, b"eastAsia")
                        .or_else(|| attr_value(&e, b"ascii"))
                        .or_else(|| attr_value(&e, b"hAnsi"));
                }
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_doc_defaults
                    && (e.local_name().as_ref() == b"sz" || e.local_name().as_ref() == b"szCs") =>
            {
                if defaults.size_pt.is_none() {
                    defaults.size_pt = attr_value(&e, b"val").and_then(|v| parse_size_pt(&v));
                }
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_style && e.local_name().as_ref() == b"basedOn" =>
            {
                current_style_parent = attr_value(&e, b"val");
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_style && e.local_name().as_ref() == b"rFonts" =>
            {
                current_style_format.font = attr_value(&e, b"eastAsia")
                    .or_else(|| attr_value(&e, b"ascii"))
                    .or_else(|| attr_value(&e, b"hAnsi"))
                    .or_else(|| current_style_format.font.clone());
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_style
                    && (e.local_name().as_ref() == b"sz" || e.local_name().as_ref() == b"szCs") =>
            {
                current_style_format.size_pt =
                    attr_value(&e, b"val").and_then(|v| parse_size_pt(&v));
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_style && e.local_name().as_ref() == b"b" =>
            {
                current_style_format.bold = Some(true);
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_style && e.local_name().as_ref() == b"color" =>
            {
                current_style_format.color = attr_value(&e, b"val");
            }
            Ok(Event::Start(e)) | Ok(Event::Empty(e))
                if in_style && e.local_name().as_ref() == b"rStyle" =>
            {
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
