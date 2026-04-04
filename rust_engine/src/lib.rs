pub mod parser;
pub mod annotator;

#[cfg(test)]
mod tests {
    #[test]
    fn test_parser_missing() {
        let r = crate::parser::parse_document("nonexistent_file.txt", &crate::parser::ParseOptions::default());
        assert!(r.get("error").is_some());
    }

    #[test]
    fn test_annotator_copy_fail() {
        let res = crate::annotator::annotate_document("nonexistent.docx", &serde_json::json!([]), None);
        assert!(res.is_err());
    }
}

use axum::{extract::Json, routing::{get, post}, Router};
use serde::Deserialize;


#[derive(Deserialize)]
struct ParseRequest {
    #[serde(alias = "file_path")]
    input_path: String,
    #[serde(default)]
    options: Option<serde_json::Value>,
}

#[derive(Deserialize)]
struct AnnotateRequest {
    original_path: String,
    issues: Vec<serde_json::Value>,
    #[serde(default)]
    output_filename: Option<String>,
}

pub fn create_app() -> Router {
    Router::new()
        .route("/health", get(health_handler))
        .route("/parse", post(parse_handler))
        .route("/annotate", post(annotate_handler))
}

async fn health_handler() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "status": "healthy",
        "version": "0.1.0",
        "capabilities": ["docx_parse", "annotation"],
        "system": {
            "parallel_threads": std::env::var("RUST_PARALLEL_THREADS").ok().and_then(|v| v.parse::<u32>().ok()).unwrap_or(4)
        }
    }))
}

async fn parse_handler(Json(payload): Json<ParseRequest>) -> Json<serde_json::Value> {
    let options = payload
        .options
        .and_then(|value| serde_json::from_value::<crate::parser::ParseOptions>(value).ok())
        .unwrap_or_default();
    let res = parser::parse_document(&payload.input_path, &options);
    Json(res)
}

async fn annotate_handler(Json(payload): Json<AnnotateRequest>) -> Json<serde_json::Value> {
    match annotator::annotate_document(
        &payload.original_path,
        &serde_json::Value::from(payload.issues),
        payload.output_filename.as_deref(),
    ) {
        Ok(p) => Json(p),
        Err(e) => Json(serde_json::json!({"success": false, "error": e})),
    }
}
