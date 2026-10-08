use ai_inference_server_rust::build_app;

#[tokio::main]
async fn main() {
    let port = std::env::var("PORT").unwrap_or_else(|_| "3000".to_string());
    let addr = format!("0.0.0.0:{}", port);
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    eprintln!("ai-inference-server listening on {}", addr);
    axum::serve(listener, build_app()).await.unwrap();
}
