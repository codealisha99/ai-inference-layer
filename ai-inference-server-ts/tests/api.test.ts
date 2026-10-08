import { describe, it, expect, beforeEach } from 'vitest';
import { buildApp } from '../src/app.js';

function app() { return buildApp(); }

const simpleModel = { name: 'gpt-test', type: 'text-generation' };

async function createModel(a: ReturnType<typeof app>, body = simpleModel) {
  return a.inject({ method: 'POST', url: '/models', payload: body });
}

function id(r: { json(): Record<string, unknown> }) {
  return (r.json().data as Record<string, unknown>).id as string;
}

describe('health', () => {
  it('returns 200', async () => {
    const r = await app().inject({ method: 'GET', url: '/health' });
    expect(r.statusCode).toBe(200);
  });
});

describe('create model', () => {
  it('returns 201 with model data', async () => {
    const r = await createModel(app());
    expect(r.statusCode).toBe(201);
    expect(r.json().data.name).toBe('gpt-test');
  });

  it('returns 400 when name missing', async () => {
    const a = app();
    const r = await a.inject({ method: 'POST', url: '/models', payload: { type: 'embedding' } });
    expect(r.statusCode).toBe(400);
  });

  it('returns 400 when type invalid', async () => {
    const a = app();
    const r = await a.inject({ method: 'POST', url: '/models', payload: { name: 'x', type: 'badtype' } });
    expect(r.statusCode).toBe(400);
  });

  it('returns 400 when type missing', async () => {
    const a = app();
    const r = await a.inject({ method: 'POST', url: '/models', payload: { name: 'x' } });
    expect(r.statusCode).toBe(400);
  });

  it('returns 409 on duplicate name', async () => {
    const a = app();
    await createModel(a);
    const r = await createModel(a);
    expect(r.statusCode).toBe(409);
  });

  it('accepts all valid types', async () => {
    const a = app();
    for (const type of ['text-generation', 'text-classification', 'embedding']) {
      const r = await a.inject({ method: 'POST', url: '/models', payload: { name: type, type } });
      expect(r.statusCode).toBe(201);
    }
  });
});

describe('list models', () => {
  it('returns empty list initially', async () => {
    const r = await app().inject({ method: 'GET', url: '/models' });
    expect(r.statusCode).toBe(200);
    expect(r.json().data).toEqual([]);
  });

  it('returns all created models', async () => {
    const a = app();
    await createModel(a, { name: 'm1', type: 'embedding' });
    await createModel(a, { name: 'm2', type: 'text-classification' });
    const r = await a.inject({ method: 'GET', url: '/models' });
    expect(r.json().data).toHaveLength(2);
  });
});

describe('get model', () => {
  it('returns 200 for existing model', async () => {
    const a = app();
    const modelId = id(await createModel(a));
    const r = await a.inject({ method: 'GET', url: `/models/${modelId}` });
    expect(r.statusCode).toBe(200);
  });

  it('returns 404 for unknown id', async () => {
    const r = await app().inject({ method: 'GET', url: '/models/nope' });
    expect(r.statusCode).toBe(404);
  });
});

describe('delete model', () => {
  it('removes model and returns 200', async () => {
    const a = app();
    const modelId = id(await createModel(a));
    const r = await a.inject({ method: 'DELETE', url: `/models/${modelId}` });
    expect(r.statusCode).toBe(200);
    const check = await a.inject({ method: 'GET', url: `/models/${modelId}` });
    expect(check.statusCode).toBe(404);
  });

  it('returns 404 for unknown id', async () => {
    const r = await app().inject({ method: 'DELETE', url: '/models/nope' });
    expect(r.statusCode).toBe(404);
  });
});

describe('infer', () => {
  it('returns 201 with completed output', async () => {
    const a = app();
    const modelId = id(await createModel(a));
    const r = await a.inject({ method: 'POST', url: `/models/${modelId}/infer`, payload: { input: 'hello' } });
    expect(r.statusCode).toBe(201);
    expect(r.json().data.status).toBe('completed');
    expect(r.json().data.output).toBeTruthy();
  });

  it('text-generation produces text output', async () => {
    const a = app();
    const modelId = id(await createModel(a, { name: 'gen', type: 'text-generation' }));
    const r = await a.inject({ method: 'POST', url: `/models/${modelId}/infer`, payload: { input: 'hi' } });
    expect(r.json().data.output.text).toBeTruthy();
  });

  it('text-classification produces label and score', async () => {
    const a = app();
    const modelId = id(await createModel(a, { name: 'cls', type: 'text-classification' }));
    const r = await a.inject({ method: 'POST', url: `/models/${modelId}/infer`, payload: { input: 'hi' } });
    expect(r.json().data.output.label).toBeTruthy();
    expect(typeof r.json().data.output.score).toBe('number');
  });

  it('embedding produces embedding array', async () => {
    const a = app();
    const modelId = id(await createModel(a, { name: 'emb', type: 'embedding' }));
    const r = await a.inject({ method: 'POST', url: `/models/${modelId}/infer`, payload: { input: 'hi' } });
    expect(Array.isArray(r.json().data.output.embedding)).toBe(true);
  });

  it('returns 400 when input missing', async () => {
    const a = app();
    const modelId = id(await createModel(a));
    const r = await a.inject({ method: 'POST', url: `/models/${modelId}/infer`, payload: {} });
    expect(r.statusCode).toBe(400);
  });

  it('returns 404 for unknown model', async () => {
    const r = await app().inject({ method: 'POST', url: '/models/nope/infer', payload: { input: 'hi' } });
    expect(r.statusCode).toBe(404);
  });
});

describe('list inferences', () => {
  it('returns list of inferences', async () => {
    const a = app();
    const modelId = id(await createModel(a));
    await a.inject({ method: 'POST', url: `/models/${modelId}/infer`, payload: { input: 'a' } });
    await a.inject({ method: 'POST', url: `/models/${modelId}/infer`, payload: { input: 'b' } });
    const r = await a.inject({ method: 'GET', url: `/models/${modelId}/inferences` });
    expect(r.statusCode).toBe(200);
    expect(r.json().data).toHaveLength(2);
  });

  it('returns 404 for unknown model', async () => {
    const r = await app().inject({ method: 'GET', url: '/models/nope/inferences' });
    expect(r.statusCode).toBe(404);
  });
});

describe('get inference', () => {
  it('returns inference by id', async () => {
    const a = app();
    const modelId = id(await createModel(a));
    const ir = await a.inject({ method: 'POST', url: `/models/${modelId}/infer`, payload: { input: 'x' } });
    const infId = (ir.json().data as Record<string, unknown>).id as string;
    const r = await a.inject({ method: 'GET', url: `/models/${modelId}/inferences/${infId}` });
    expect(r.statusCode).toBe(200);
  });

  it('returns 404 for unknown inference', async () => {
    const a = app();
    const modelId = id(await createModel(a));
    const r = await a.inject({ method: 'GET', url: `/models/${modelId}/inferences/nope` });
    expect(r.statusCode).toBe(404);
  });

  it('returns 404 for unknown model', async () => {
    const r = await app().inject({ method: 'GET', url: '/models/nope/inferences/x' });
    expect(r.statusCode).toBe(404);
  });
});
