use serde::Deserialize;

#[derive(Default, Deserialize)]
pub struct ParseOptions {
    pub extract_styles: bool,
    pub compute_coordinates: bool,
    pub extract_images: bool,
}

#[derive(Default, Clone)]
pub(crate) struct TextFormat {
    pub(crate) font: Option<String>,
    pub(crate) size_pt: Option<String>,
    pub(crate) bold: Option<bool>,
    pub(crate) color: Option<String>,
    pub(crate) style: Option<String>,
}

#[derive(Default, Clone)]
pub(crate) struct StyleInfo {
    pub(crate) parent: Option<String>,
    pub(crate) format: TextFormat,
}

#[derive(Default, Clone)]
pub(crate) struct RunInfo {
    pub(crate) text: String,
    pub(crate) format: TextFormat,
}

#[derive(Default, Clone)]
pub(crate) struct ParagraphInfo {
    pub(crate) text: String,
    pub(crate) runs: Vec<RunInfo>,
    pub(crate) format: TextFormat,
}

#[derive(Default, Clone)]
pub(crate) struct SectionInfo {
    pub(crate) element_type: String,
    pub(crate) text: String,
    pub(crate) runs: Vec<RunInfo>,
    pub(crate) format: TextFormat,
    pub(crate) table_rows: Vec<Vec<String>>,
    pub(crate) images: Vec<String>,
    pub(crate) has_math: bool,
    pub(crate) is_table: bool,
    pub(crate) paragraph_style: Option<String>,
}
