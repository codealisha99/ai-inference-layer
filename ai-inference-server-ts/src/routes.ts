import { FastifyInstance } from 'fastify';
import { InferenceStore, VALID_TYPES, ModelType } from './inference.js';

function ok(data: unknown) {
  return { success: true, data, error: null };
}
function fail(error: string) {
  return { success: false, data: null, error };
}

export function registerRoutes(app: FastifyInstance, store: InferenceStore) {
  app.get('/health', async () => ok({ status: 'ok' }));

  app.post('/models', async (req, reply) => {
    const body = req.body as Record<string, unknown>;
    const name = body?.name as string | undefined;
    if (!name) return reply.status(400).send(fail('name is required'));
    const type = body?.type as string | undefined;
    if (!type || !VALID_TYPES.has(type as ModelType)) {
      return reply.status(400).send(fail('type must be one of: text-generation, text-classification, embedding'));
    }
    const config = (body?.config as Record<string, unknown>) ?? {};
    const model = store.createModel(name, type as ModelType, config);
    if (!model) return reply.status(409).send(fail('model with that name already exists'));
    return reply.status(201).send(ok(model));
  });

  app.get('/models', async () => ok(store.listModels()));

  app.get('/models/:id', async (req, reply) => {
    const { id } = req.params as { id: string };
    const model = store.getModel(id);
    if (!model) return reply.status(404).send(fail('model not found'));
    return ok(model);
  });

  app.delete('/models/:id', async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!store.deleteModel(id)) return reply.status(404).send(fail('model not found'));
    return ok({ id, removed: true });
  });

  app.post('/models/:id/infer', async (req, reply) => {
    const { id } = req.params as { id: string };
    const body = req.body as Record<string, unknown>;
    const input = body?.input as string | undefined;
    if (!input) return reply.status(400).send(fail('input is required'));
    const inf = store.runInference(id, input);
    if (!inf) return reply.status(404).send(fail('model not found'));
    return reply.status(201).send(ok(inf));
  });

  app.get('/models/:id/inferences', async (req, reply) => {
    const { id } = req.params as { id: string };
    const list = store.listInferences(id);
    if (!list) return reply.status(404).send(fail('model not found'));
    return ok(list);
  });

  app.get('/models/:id/inferences/:inferenceId', async (req, reply) => {
    const { id, inferenceId } = req.params as { id: string; inferenceId: string };
    const { inf, modelFound } = store.getInference(id, inferenceId);
    if (!modelFound) return reply.status(404).send(fail('model not found'));
    if (!inf) return reply.status(404).send(fail('inference not found'));
    return ok(inf);
  });
}
