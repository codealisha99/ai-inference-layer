import { buildApp } from '../app.js';

const port = parseInt(process.env.PORT ?? '3000', 10);
const app = buildApp();
await app.listen({ port, host: '0.0.0.0' });
console.error(`ai-inference-server listening on :${port}`);
