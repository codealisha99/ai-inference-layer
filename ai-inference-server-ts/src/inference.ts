let idCounter = 0;
function newId(): string {
  return `${Date.now().toString(16)}${(++idCounter).toString(16)}`;
}

export type ModelType = 'text-generation' | 'text-classification' | 'embedding';

export const VALID_TYPES = new Set<ModelType>([
  'text-generation',
  'text-classification',
  'embedding',
]);

export interface Model {
  id: string;
  name: string;
  type: ModelType;
  config: Record<string, unknown>;
  createdAt: number;
}

export type InferenceStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Inference {
  id: string;
  modelId: string;
  input: string;
  status: InferenceStatus;
  output: Record<string, unknown> | null;
  createdAt: number;
  completedAt: number | null;
}

function simulate(type: ModelType, input: string): Record<string, unknown> {
  switch (type) {
    case 'text-generation':
      return { text: `Generated response for: ${input}` };
    case 'text-classification':
      return { label: 'positive', score: 0.95 };
    case 'embedding':
      return { embedding: [0.1, 0.2, 0.3, 0.4, 0.5] };
  }
}

export class InferenceStore {
  private models = new Map<string, Model>();
  private inferences = new Map<string, Map<string, Inference>>();

  createModel(name: string, type: ModelType, config: Record<string, unknown>): Model | null {
    for (const m of this.models.values()) {
      if (m.name === name) return null;
    }
    const id = newId();
    const model: Model = { id, name, type, config, createdAt: Date.now() };
    this.models = new Map(this.models).set(id, model);
    this.inferences = new Map(this.inferences).set(id, new Map());
    return model;
  }

  getModel(id: string): Model | undefined {
    return this.models.get(id);
  }

  listModels(): Model[] {
    return Array.from(this.models.values());
  }

  deleteModel(id: string): boolean {
    if (!this.models.has(id)) return false;
    const next = new Map(this.models);
    next.delete(id);
    this.models = next;
    const nextInf = new Map(this.inferences);
    nextInf.delete(id);
    this.inferences = nextInf;
    return true;
  }

  runInference(modelId: string, input: string): Inference | null {
    const model = this.models.get(modelId);
    if (!model) return null;
    const now = Date.now();
    const inf: Inference = {
      id: newId(),
      modelId,
      input,
      status: 'completed',
      output: simulate(model.type, input),
      createdAt: now,
      completedAt: now,
    };
    const bucket = new Map(this.inferences.get(modelId)!).set(inf.id, inf);
    this.inferences = new Map(this.inferences).set(modelId, bucket);
    return inf;
  }

  listInferences(modelId: string): Inference[] | null {
    const bucket = this.inferences.get(modelId);
    if (!bucket) return null;
    return Array.from(bucket.values());
  }

  getInference(modelId: string, inferenceId: string): { inf?: Inference; modelFound: boolean } {
    const bucket = this.inferences.get(modelId);
    if (!bucket) return { modelFound: false };
    return { inf: bucket.get(inferenceId), modelFound: true };
  }
}
