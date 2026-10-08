use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

static ID_COUNTER: AtomicU64 = AtomicU64::new(0);

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_millis() as u64
}

fn new_id() -> String {
    let t = now_ms();
    let n = ID_COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{:x}{:x}", t ^ n, n)
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum ModelType {
    TextGeneration,
    TextClassification,
    Embedding,
}

impl ModelType {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "text-generation" => Some(Self::TextGeneration),
            "text-classification" => Some(Self::TextClassification),
            "embedding" => Some(Self::Embedding),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Model {
    pub id: String,
    pub name: String,
    pub r#type: ModelType,
    pub config: serde_json::Value,
    pub created_at: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Inference {
    pub id: String,
    pub model_id: String,
    pub input: String,
    pub status: String,
    pub output: serde_json::Value,
    pub created_at: u64,
    pub completed_at: u64,
}

fn simulate(t: &ModelType, input: &str) -> serde_json::Value {
    match t {
        ModelType::TextGeneration => {
            serde_json::json!({"text": format!("Generated response for: {}", input)})
        }
        ModelType::TextClassification => {
            serde_json::json!({"label": "positive", "score": 0.95})
        }
        ModelType::Embedding => {
            serde_json::json!({"embedding": [0.1, 0.2, 0.3, 0.4, 0.5]})
        }
    }
}

#[derive(Clone)]
pub struct InferenceStore {
    inner: Arc<RwLock<StoreInner>>,
}

struct StoreInner {
    models: HashMap<String, Model>,
    inferences: HashMap<String, HashMap<String, Inference>>,
}

impl InferenceStore {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(StoreInner {
                models: HashMap::new(),
                inferences: HashMap::new(),
            })),
        }
    }

    pub fn create(
        &self,
        name: String,
        model_type: ModelType,
        config: serde_json::Value,
    ) -> Result<Model, &'static str> {
        let mut inner = self.inner.write().unwrap();
        if inner.models.values().any(|m| m.name == name) {
            return Err("duplicate");
        }
        let id = new_id();
        let m = Model {
            id: id.clone(),
            name,
            r#type: model_type,
            config,
            created_at: now_ms(),
        };
        inner.models.insert(id.clone(), m.clone());
        inner.inferences.insert(id, HashMap::new());
        Ok(m)
    }

    pub fn get(&self, id: &str) -> Option<Model> {
        self.inner.read().unwrap().models.get(id).cloned()
    }

    pub fn list(&self) -> Vec<Model> {
        self.inner.read().unwrap().models.values().cloned().collect()
    }

    pub fn delete(&self, id: &str) -> bool {
        let mut inner = self.inner.write().unwrap();
        if inner.models.remove(id).is_none() {
            return false;
        }
        inner.inferences.remove(id);
        true
    }

    pub fn run_inference(&self, model_id: &str, input: String) -> Option<Inference> {
        let mut inner = self.inner.write().unwrap();
        let model = inner.models.get(model_id)?.clone();
        let now = now_ms();
        let inf = Inference {
            id: new_id(),
            model_id: model_id.to_string(),
            input: input.clone(),
            status: "completed".to_string(),
            output: simulate(&model.r#type, &input),
            created_at: now,
            completed_at: now,
        };
        inner
            .inferences
            .get_mut(model_id)
            .unwrap()
            .insert(inf.id.clone(), inf.clone());
        Some(inf)
    }

    pub fn list_inferences(&self, model_id: &str) -> Option<Vec<Inference>> {
        let inner = self.inner.read().unwrap();
        inner
            .inferences
            .get(model_id)
            .map(|m| m.values().cloned().collect())
    }

    pub fn get_inference(&self, model_id: &str, inference_id: &str) -> Result<Inference, bool> {
        let inner = self.inner.read().unwrap();
        match inner.inferences.get(model_id) {
            None => Err(false),
            Some(m) => m.get(inference_id).cloned().ok_or(true),
        }
    }
}
