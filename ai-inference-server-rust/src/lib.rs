pub mod inference;
pub mod routes;

use axum::{
    routing::{delete, get, post},
    Router,
};
use inference::InferenceStore;

pub fn build_app() -> Router {
    let store = InferenceStore::new();
    Router::new()
        .route("/health", get(routes::health))
        .route("/models", post(routes::create_model))
        .route("/models", get(routes::list_models))
        .route("/models/:id", get(routes::get_model))
        .route("/models/:id", delete(routes::delete_model))
        .route("/models/:id/infer", post(routes::run_inference))
        .route("/models/:id/inferences", get(routes::list_inferences))
        .route("/models/:id/inferences/:inferenceId", get(routes::get_inference))
        .with_state(store)
}
