use axum::body::{to_bytes, Body};
use axum::http::{Request, StatusCode};
use tower::util::ServiceExt;
use serde_json::json;

#[tokio::test]
async fn test_health_endpoint() {
    let app = paper_audit_rust::create_app();
    let req = Request::builder()
        .method("GET")
        .uri("/health")
        .body(Body::empty())
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(v.get("status").and_then(|s| s.as_str()).unwrap(), "healthy");
}

#[tokio::test]
async fn test_parse_and_annotate_flow() {
    use std::fs::{self, File};
    use std::io::Write;
    use tempfile::tempdir;

    let dir = tempdir().unwrap();
    let file_path = dir.path().join("doc.txt");
    let mut f = File::create(&file_path).unwrap();
    writeln!(f, "This is a test document.").unwrap();
    let file_path_str = file_path.to_string_lossy().to_string();

    let app = paper_audit_rust::create_app();

    // POST /parse
    let body = json!({"file_path": file_path_str}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/parse")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert!(v.get("sections").is_some());

    // POST /annotate
    let body = json!({"original_path": file_path_str, "issues": []}).to_string();
    let req = Request::builder()
        .method("POST")
        .uri("/annotate")
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();
    let resp = app.clone().oneshot(req).await.unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let bytes = to_bytes(resp.into_body(), usize::MAX).await.unwrap();
    let v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert!(v.get("output_path").is_some());

    // verify output file exists
    let out = v.get("output_path").and_then(|p| p.as_str()).unwrap();
    assert!(std::path::Path::new(out).exists());

    // cleanup
    let _ = fs::remove_file(out);
}
