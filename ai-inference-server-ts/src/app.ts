import Fastify from 'fastify';
import { InferenceStore } from './inference.js';
import { registerRoutes } from './routes.js';

export function buildApp() {
  const app = Fastify();
  const store = new InferenceStore();
  registerRoutes(app, store);
  return app;
}
