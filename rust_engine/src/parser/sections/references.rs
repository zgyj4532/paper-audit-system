use serde_json::json;

use super::super::types::SectionInfo;

fn parse_pt_value(size_pt: Option<&str>) -> Option<f64> {
    size_pt
        .and_then(|value| value.strip_suffix("pt"))
        .and_then(|value| value.parse::<f64>().ok())
}

fn is_heading_like_terminator(section: &SectionInfo, text: &str) -> bool {
    let normalized = text.trim();
    if normalized.is_empty() || normalized.len() > 30 {
        return false;
    }

    let has_heading_style = section
        .format
        .style
        .as_deref()
        .map(|style| style.to_lowercase().contains("heading"))
        .unwrap_or(false);
    if has_heading_style {
        return true;
    }

    let size_pt = parse_pt_value(section.format.size_pt.as_deref()).unwrap_or(0.0);
    let bold = section.format.bold.unwrap_or(false);
    let title_like = !normalized.contains('。')
        && !normalized.contains('.')
        && !normalized.contains('，')
        && !normalized.contains(',')
        && !normalized.contains('；')
        && !normalized.contains(';');

    title_like && (size_pt >= 14.0 || (bold && size_pt >= 12.0))
}

pub(crate) fn is_reference_heading(text: &str) -> bool {
    let normalized = text.trim().trim_matches('：').trim_matches(':');
    normalized == "参考文献"
}

pub(crate) fn is_reference_ending_section(section: &SectionInfo, text: &str) -> bool {
    let normalized = text.trim();
    if normalized.is_empty() {
        return false;
    }

    if section.is_table {
        return true;
    }

    let stop_prefixes = ["作者简介", "致谢", "附录"];
    if stop_prefixes
        .iter()
        .any(|prefix| normalized.starts_with(prefix))
    {
        return true;
    }

    is_heading_like_terminator(section, text)
}

pub(crate) fn extract_references(sections_input: &[SectionInfo]) -> Vec<serde_json::Value> {
    let mut references = Vec::new();
    let mut in_reference_block = false;

    for (index, section) in sections_input.iter().enumerate() {
        let text = section.text.trim();
        if text.is_empty() {
            continue;
        }

        if !in_reference_block {
            if is_reference_heading(text) {
                in_reference_block = true;
            }
            continue;
        }

        if is_reference_ending_section(section, text) {
            break;
        }

        let reference_index = references.len() + 1;
        let page_start = section.page_start.unwrap_or((index / 20) + 1);
        let page_end = section.page_end.unwrap_or(page_start);
        references.push(json!({
            "index": reference_index,
            "ref_id": format!("[{}]", reference_index),
            "text": text,
            "raw_text": text,
            "section_id": index + 1,
            "page_start": page_start,
            "page_end": page_end
        }));
    }

    references
}
