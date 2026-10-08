use axum_test::TestServer;
use ai_inference_server_rust::build_app;
use serde_json::{json, Value};

fn server() -> TestServer {
    TestServer::new(build_app()).unwrap()
}

async fn create_model(s: &TestServer, name: &str, typ: &str) -> Value {
    s.post("/models")
        .json(&json!({"name": name, "type": typ}))
        .await
        .json::<Value>()
}

fn id(v: &Value) -> String {
    v["data"]["id"].as_str().unwrap().to_string()
}

#[tokio::test]
async fn test_health() {
    let s = server();
    let r = s.get("/health").await;
    assert_eq!(r.status_code(), 200);
}

#[tokio::test]
async fn test_create_model() {
    let s = server();
    let r = s.post("/models").json(&json!({"name": "gpt", "type": "text-generation"})).await;
    assert_eq!(r.status_code(), 201);
    let v: Value = r.json();
    assert_eq!(v["data"]["name"], "gpt");
}

#[tokio::test]
async fn test_create_model_missing_name() {
    let s = server();
    let r = s.post("/models").json(&json!({"type": "embedding"})).await;
    assert_eq!(r.status_code(), 400);
}

#[tokio::test]
async fn test_create_model_invalid_type() {
    let s = server();
    let r = s.post("/models").json(&json!({"name": "x", "type": "badtype"})).await;
    assert_eq!(r.status_code(), 400);
}

#[tokio::test]
async fn test_create_model_missing_type() {
    let s = server();
    let r = s.post("/models").json(&json!({"name": "x"})).await;
    assert_eq!(r.status_code(), 400);
}

#[tokio::test]
async fn test_create_model_duplicate() {
    let s = server();
    create_model(&s, "gpt", "text-generation").await;
    let r = s.post("/models").json(&json!({"name": "gpt", "type": "text-generation"})).await;
    assert_eq!(r.status_code(), 409);
}

#[tokio::test]
async fn test_create_model_all_types() {
    for typ in ["text-generation", "text-classification", "embedding"] {
        let s = server();
        let r = s.post("/models").json(&json!({"name": "m", "type": typ})).await;
        assert_eq!(r.status_code(), 201, "type {} failed", typ);
    }
}

#[tokio::test]
async fn test_list_models() {
    let s = server();
    create_model(&s, "m1", "embedding").await;
    create_model(&s, "m2", "text-classification").await;
    let r = s.get("/models").await;
    assert_eq!(r.status_code(), 200);
    let v: Value = r.json();
    assert_eq!(v["data"].as_array().unwrap().len(), 2);
}

#[tokio::test]
async fn test_get_model() {
    let s = server();
    let v = create_model(&s, "gpt", "text-generation").await;
    let r = s.get(&format!("/models/{}", id(&v))).await;
    assert_eq!(r.status_code(), 200);
}

#[tokio::test]
async fn test_get_model_not_found() {
    let s = server();
    let r = s.get("/models/nope").await;
    assert_eq!(r.status_code(), 404);
}

#[tokio::test]
async fn test_delete_model() {
    let s = server();
    let v = create_model(&s, "gpt", "text-generation").await;
    let mid = id(&v);
    let r = s.delete(&format!("/models/{}", mid)).await;
    assert_eq!(r.status_code(), 200);
    let check = s.get(&format!("/models/{}", mid)).await;
    assert_eq!(check.status_code(), 404);
}

#[tokio::test]
async fn test_delete_model_not_found() {
    let s = server();
    let r = s.delete("/models/nope").await;
    assert_eq!(r.status_code(), 404);
}

#[tokio::test]
async fn test_run_inference() {
    let s = server();
    let v = create_model(&s, "gpt", "text-generation").await;
    let r = s.post(&format!("/models/{}/infer", id(&v)))
        .json(&json!({"input": "hello"}))
        .await;
    assert_eq!(r.status_code(), 201);
    let rv: Value = r.json();
    assert_eq!(rv["data"]["status"], "completed");
    assert!(!rv["data"]["output"].is_null());
}

#[tokio::test]
async fn test_run_inference_missing_input() {
    let s = server();
    let v = create_model(&s, "gpt", "text-generation").await;
    let r = s.post(&format!("/models/{}/infer", id(&v)))
        .json(&json!({}))
        .await;
    assert_eq!(r.status_code(), 400);
}

#[tokio::test]
async fn test_run_inference_not_found() {
    let s = server();
    let r = s.post("/models/nope/infer").json(&json!({"input": "hi"})).await;
    assert_eq!(r.status_code(), 404);
}

#[tokio::test]
async fn test_text_generation_output() {
    let s = server();
    let v = create_model(&s, "gen", "text-generation").await;
    let r = s.post(&format!("/models/{}/infer", id(&v)))
        .json(&json!({"input": "hi"}))
        .await;
    let rv: Value = r.json();
    assert!(!rv["data"]["output"]["text"].is_null());
}

#[tokio::test]
async fn test_text_classification_output() {
    let s = server();
    let v = create_model(&s, "cls", "text-classification").await;
    let r = s.post(&format!("/models/{}/infer", id(&v)))
        .json(&json!({"input": "hi"}))
        .await;
    let rv: Value = r.json();
    assert!(!rv["data"]["output"]["label"].is_null());
    assert!(rv["data"]["output"]["score"].is_number());
}

#[tokio::test]
async fn test_embedding_output() {
    let s = server();
    let v = create_model(&s, "emb", "embedding").await;
    let r = s.post(&format!("/models/{}/infer", id(&v)))
        .json(&json!({"input": "hi"}))
        .await;
    let rv: Value = r.json();
    assert!(rv["data"]["output"]["embedding"].is_array());
}

#[tokio::test]
async fn test_list_inferences() {
    let s = server();
    let v = create_model(&s, "gpt", "text-generation").await;
    let mid = id(&v);
    s.post(&format!("/models/{}/infer", mid)).json(&json!({"input": "a"})).await;
    s.post(&format!("/models/{}/infer", mid)).json(&json!({"input": "b"})).await;
    let r = s.get(&format!("/models/{}/inferences", mid)).await;
    assert_eq!(r.status_code(), 200);
    let rv: Value = r.json();
    assert_eq!(rv["data"].as_array().unwrap().len(), 2);
}

#[tokio::test]
async fn test_list_inferences_not_found() {
    let s = server();
    let r = s.get("/models/nope/inferences").await;
    assert_eq!(r.status_code(), 404);
}

#[tokio::test]
async fn test_get_inference() {
    let s = server();
    let v = create_model(&s, "gpt", "text-generation").await;
    let mid = id(&v);
    let ir: Value = s.post(&format!("/models/{}/infer", mid))
        .json(&json!({"input": "x"}))
        .await
        .json();
    let inf_id = ir["data"]["id"].as_str().unwrap();
    let r = s.get(&format!("/models/{}/inferences/{}", mid, inf_id)).await;
    assert_eq!(r.status_code(), 200);
}

#[tokio::test]
async fn test_get_inference_not_found() {
    let s = server();
    let v = create_model(&s, "gpt", "text-generation").await;
    let r = s.get(&format!("/models/{}/inferences/nope", id(&v))).await;
    assert_eq!(r.status_code(), 404);
}

#[tokio::test]
async fn test_get_inference_model_not_found() {
    let s = server();
    let r = s.get("/models/nope/inferences/x").await;
    assert_eq!(r.status_code(), 404);
}
