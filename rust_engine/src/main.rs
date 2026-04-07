use paper_audit_rust::create_app;
use std::net::SocketAddr;

#[tokio::main]
async fn main() {
    let port = std::env::var("RUST_HTTP_PORT")
        .ok()
        .and_then(|s| s.parse::<u16>().ok())
        .unwrap_or(8193);
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    let app = create_app();

    println!("rust engine listening on {}", addr);
    axum::serve(listener, app).await.unwrap();
}
