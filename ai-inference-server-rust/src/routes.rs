use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::inference::{InferenceStore, ModelType};

fn ok(data: impl serde::Serialize) -> impl IntoResponse {
    (
        StatusCode::OK,
        Json(json!({"success": true, "data": data, "error": null})),
    )
}

fn created(data: impl serde::Serialize) -> impl IntoResponse {
    (
        StatusCode::CREATED,
        Json(json!({"success": true, "data": data, "error": null})),
    )
}

fn bad_req(msg: &str) -> impl IntoResponse {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"success": false, "data": null, "error": msg})),
    )
}

fn not_found(msg: &str) -> impl IntoResponse {
    (
        StatusCode::NOT_FOUND,
        Json(json!({"success": false, "data": null, "error": msg})),
    )
}

fn conflict(msg: &str) -> impl IntoResponse {
    (
        StatusCode::CONFLICT,
        Json(json!({"success": false, "data": null, "error": msg})),
    )
}

pub async fn health() -> impl IntoResponse {
    ok(json!({"status": "ok"}))
}

#[derive(Deserialize)]
pub struct CreateBody {
    pub name: Option<String>,
    pub r#type: Option<String>,
    #[serde(default)]
    pub config: Value,
}

pub async fn create_model(
    State(store): State<InferenceStore>,
    body: Option<Json<CreateBody>>,
) -> impl IntoResponse {
    let Json(body) = match body {
        Some(b) => b,
        None => return bad_req("invalid JSON").into_response(),
    };

    let name = match body.name.as_deref().filter(|n| !n.is_empty()) {
        Some(n) => n.to_string(),
        None => return bad_req("name is required").into_response(),
    };

    let type_str = body.r#type.as_deref().unwrap_or("");
    let model_type = match ModelType::from_str(type_str) {
        Some(t) => t,
        None => {
            return bad_req("type must be one of: text-generation, text-classification, embedding")
                .into_response()
        }
    };

    match store.create(name, model_type, body.config) {
        Ok(m) => created(m).into_response(),
        Err(_) => conflict("model with that name already exists").into_response(),
    }
}

pub async fn list_models(State(store): State<InferenceStore>) -> impl IntoResponse {
    ok(store.list())
}

pub async fn get_model(
    State(store): State<InferenceStore>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    match store.get(&id) {
        Some(m) => ok(m).into_response(),
        None => not_found("model not found").into_response(),
    }
}

pub async fn delete_model(
    State(store): State<InferenceStore>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    if store.delete(&id) {
        ok(json!({"id": id, "removed": true})).into_response()
    } else {
        not_found("model not found").into_response()
    }
}

#[derive(Deserialize)]
pub struct InferBody {
    pub input: Option<String>,
}

pub async fn run_inference(
    State(store): State<InferenceStore>,
    Path(id): Path<String>,
    body: Option<Json<InferBody>>,
) -> impl IntoResponse {
    let Json(body) = match body {
        Some(b) => b,
        None => return bad_req("invalid JSON").into_response(),
    };
    let input = match body.input.as_deref().filter(|s| !s.is_empty()) {
        Some(s) => s.to_string(),
        None => return bad_req("input is required").into_response(),
    };
    match store.run_inference(&id, input) {
        Some(inf) => created(inf).into_response(),
        None => not_found("model not found").into_response(),
    }
}

pub async fn list_inferences(
    State(store): State<InferenceStore>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    match store.list_inferences(&id) {
        Some(list) => ok(list).into_response(),
        None => not_found("model not found").into_response(),
    }
}

pub async fn get_inference(
    State(store): State<InferenceStore>,
    Path((id, inference_id)): Path<(String, String)>,
) -> impl IntoResponse {
    match store.get_inference(&id, &inference_id) {
        Ok(inf) => ok(inf).into_response(),
        Err(false) => not_found("model not found").into_response(),
        Err(true) => not_found("inference not found").into_response(),
    }
}
