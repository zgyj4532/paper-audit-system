use serde_json::json;

use super::types::TextFormat;

pub(crate) fn parse_size_pt(val: &str) -> Option<String> {
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

pub(crate) fn merge_format(base: &TextFormat, overlay: &TextFormat) -> TextFormat {
    TextFormat {
        font: overlay.font.clone().or_else(|| base.font.clone()),
        size_pt: overlay.size_pt.clone().or_else(|| base.size_pt.clone()),
        bold: overlay.bold.or(base.bold),
        color: overlay.color.clone().or_else(|| base.color.clone()),
        style: overlay.style.clone().or_else(|| base.style.clone()),
    }
}

pub(crate) fn format_to_json(format: &TextFormat, fallback_alignment: &str) -> serde_json::Value {
    json!({
        "font": format.font.clone().unwrap_or_else(|| "unknown".to_string()),
        "size": format.size_pt.clone().unwrap_or_else(|| "unknown".to_string()),
        "bold": format.bold.unwrap_or(false),
        "alignment": fallback_alignment,
    })
}
