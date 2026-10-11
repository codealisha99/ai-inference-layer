import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const views = [320, 375, 390, 430, 768, 1024, 1440, 1600];

test('real inference, history, model recovery, and all three engine outputs', async ({ page, request }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('[data-status-text]')).toContainText('API online');
  for (const [name, type] of [['Classify', 'text-classification'], ['Generate', 'text-generation'], ['Embed', 'embedding']]) {
    await page.getByLabel(name, { exact: true }).check();
    await page.getByLabel('Input text', { exact: true }).fill('This product is great!');
    await page.getByRole('button', { name: 'Run inference', exact: true }).click();
    await expect(page.locator('#status')).toHaveText('HTTP 201');
    const response = JSON.parse(await page.locator('#res').innerText());
    expect(response.success).toBe(true);
    expect(response.data.input).toBe('This product is great!');
    const history = await request.get(`/models/${response.data.modelId}/inferences/${response.data.id}`);
    expect((await history.json()).data).toEqual(response.data);
    if (type === 'text-classification') expect(response.data.output.label).toBe('positive');
    if (type === 'text-generation') expect(response.data.output.text).toContain('This product is great!');
    if (type === 'embedding') expect(response.data.output.embedding).toHaveLength(5);
    await request.delete(`/models/${response.data.modelId}`);
    await page.getByRole('button', { name: 'Run inference', exact: true }).click();
    await expect(page.locator('#status')).toHaveText('HTTP 201');
  }
  expect(errors).toEqual([]);
});

test('validation, keyboard shortcut, clipboard, and visible focus', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/');
  await page.getByLabel('Input text', { exact: true }).fill('   ');
  await page.getByRole('button', { name: 'Run inference', exact: true }).click();
  await expect(page.locator('#input-error')).toHaveText('Enter some text before running an inference.');
  await expect(page.locator('#input')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.locator('#input')).toBeFocused();
  await page.locator('#input').fill('Keyboard request');
  await page.locator('#input').press('Control+Enter');
  await expect(page.locator('#status')).toHaveText('HTTP 201');
  await page.getByRole('button', { name: 'Copy JSON response' }).click();
  await expect(page.locator('#copy-response')).toHaveText('Copied');
  expect(JSON.parse(await page.evaluate(() => navigator.clipboard.readText())).success).toBe(true);
  await page.getByRole('button', { name: 'Copy repository setup commands' }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('cd ai-inference-layer/ai-inference-server-py');
  await page.keyboard.press('Tab');
  const focus = await page.evaluate(() => ({ width: getComputedStyle(document.activeElement).outlineWidth, style: getComputedStyle(document.activeElement).outlineStyle }));
  expect(focus.style).toBe('solid');
  expect(parseFloat(focus.width)).toBeGreaterThanOrEqual(2);
});

test('API-key protection is retained and credentials stay out of storage', async ({ page }) => {
  await page.goto('http://127.0.0.1:3126/');
  await page.getByRole('button', { name: 'Run inference', exact: true }).click();
  await expect(page.locator('#status')).toHaveText('HTTP 401');
  await expect(page.locator('#key-wrap')).toBeVisible();
  await expect(page.locator('#key')).toBeFocused();
  await page.locator('#key').fill('wrong-key');
  await page.getByRole('button', { name: 'Run inference', exact: true }).click();
  await expect(page.locator('#status')).toHaveText('HTTP 401');
  await page.locator('#key').fill('local-ui-test-key');
  await page.getByRole('button', { name: 'Run inference', exact: true }).click();
  await expect(page.locator('#status')).toHaveText('HTTP 201');
  expect(await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) }))).toEqual({ local: [], session: [] });
});

test('connection failures recover, clipboard failures give instructions, and loading is explicit', async ({ page }) => {
  await page.goto('/');
  await page.route('**/models', async (route) => { await route.abort('failed'); });
  await page.getByRole('button', { name: 'Run inference', exact: true }).click();
  await expect(page.locator('#response-summary')).toContainText('Check your connection');
  await expect(page.locator('#status')).toHaveText('Request failed');
  await expect(page.locator('#run')).toBeEnabled();
  await page.unroute('**/models');
  let resume;
  const gate = new Promise((resolve) => { resume = resolve; });
  await page.route('**/infer', async (route) => { await gate; await route.continue(); });
  await page.getByRole('button', { name: 'Run inference', exact: true }).click();
  await expect(page.locator('#run')).toHaveText('Running…');
  await expect(page.locator('#run')).toBeDisabled();
  await expect(page.locator('#form')).toHaveAttribute('aria-busy', 'true');
  resume();
  await expect(page.locator('#status')).toHaveText('HTTP 201');
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => Promise.reject(new Error('denied')) } }));
  await page.locator('#copy-response').click();
  await expect(page.locator('#copy-response')).toHaveText('Copy failed');
  await expect(page.locator('#announcement')).toContainText('copy it manually');
});

test('playground has no horizontal overflow and passes automated WCAG checks at every target width', async ({ page }) => {
  for (const width of views) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    await expect(page.locator('[data-status-text]')).toContainText('API online');
    await page.evaluate(() => document.fonts.ready);
    const dimensions = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
    expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
    const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(audit.violations.map((issue) => ({ id: issue.id, nodes: issue.nodes.map((node) => node.target) }))).toEqual([]);
    await page.screenshot({ path: `test-results/playground-${width}.png`, fullPage: true });
  }
});

for (const path of ['/docs', '/redoc']) {
  for (const width of [320, 390, 768, 1440]) {
    test(`${path} loads real documentation and passes accessibility at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      await expect(page.locator('#docs-feedback')).toBeHidden({ timeout: 35000 });
      await expect(page.locator('#api-reference')).toContainText('Register, list, inspect and delete models.');
      await expect(page.getByRole('link', { name: 'Inference home' })).toBeVisible();
      await expect(page.locator('.docs-tabs [aria-current="page"]')).toHaveAttribute('href', path);
      const dimensions = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
      expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
      const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(audit.violations.map((issue) => ({ id: issue.id, nodes: issue.nodes.map((node) => node.target) }))).toEqual([]);
      await page.screenshot({ path: `test-results/${path.slice(1)}-${width}.png`, fullPage: true });
      await page.screenshot({ path: `test-results/${path.slice(1)}-${width}-viewport.png` });
    });
  }
}

test('documentation loader shows a recoverable error when its CDN is unreachable', async ({ page }) => {
  await page.route('https://cdn.jsdelivr.net/**', (route) => route.abort('failed'));
  await page.goto('/docs');
  await expect(page.locator('#docs-message')).toContainText('Could not load');
  await expect(page.locator('#docs-retry')).toBeVisible();
  await page.unroute('https://cdn.jsdelivr.net/**');
  await page.locator('#docs-retry').click();
  await expect(page.locator('#docs-feedback')).toBeHidden({ timeout: 35000 });
});

test('Swagger sends authenticated requests to the real API', async ({ page }) => {
  await page.goto('http://127.0.0.1:3126/docs');
  await expect(page.locator('#docs-feedback')).toBeHidden({ timeout: 35000 });
  await page.locator('.opblock-tag[data-tag="models"]').click();
  const operation = page.locator('.opblock-get').filter({ has: page.locator('.opblock-summary-path', { hasText: /^\/models$/ }) });
  await operation.locator('.opblock-summary-control').click();
  await operation.getByRole('button', { name: 'Try it out' }).click();
  const unauthorized = page.waitForResponse((response) => new URL(response.url()).pathname === '/models' && response.request().method() === 'GET');
  await operation.getByRole('button', { name: 'Execute', exact: true }).click();
  expect((await unauthorized).status()).toBe(401);
  await page.locator('#docs-key').fill('local-ui-test-key');
  const authorized = page.waitForResponse((response) => new URL(response.url()).pathname === '/models' && response.request().method() === 'GET');
  await operation.getByRole('button', { name: 'Execute', exact: true }).click();
  const response = await authorized;
  expect(response.status()).toBe(200);
  expect((await response.json()).success).toBe(true);
  await operation.locator('.operation-link').click();
  await expect(page).toHaveURL(/#\/models\/list_models_models_get$/);
  await page.setViewportSize({ width: 320, height: 900 });
  const dimensions = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
  expect(audit.violations.map((issue) => ({ id: issue.id, nodes: issue.nodes.map((node) => node.target) }))).toEqual([]);
});

test('reduced-motion preference removes interface transitions', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const duration = await page.locator('#run').evaluate((button) => getComputedStyle(button).transitionDuration);
  expect(duration.split(',').every((value) => parseFloat(value) <= 0.001)).toBe(true);
});

test('a pending request keeps its input and credentials stable and its response uncopyable', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await page.goto('/');
  await page.locator('#key-toggle').click();
  await page.locator('#key').fill('tab-key');
  await page.locator('#run').click();
  await expect(page.locator('#status')).toHaveText('HTTP 201');
  await page.locator('#copy-response').click();
  let resume;
  const gate = new Promise((resolve) => { resume = resolve; });
  await page.route('**/infer', async (route) => {
    expect(route.request().headers()['x-api-key']).toBe('tab-key');
    await gate;
    await route.continue();
  });
  await page.locator('#run').click();
  await expect(page.locator('#input')).toHaveAttribute('readonly', '');
  await expect(page.locator('#key')).toHaveAttribute('readonly', '');
  await expect(page.locator('#copy-response')).toHaveText('Copy JSON');
  await expect(page.locator('#copy-response')).toBeDisabled();
  resume();
  await expect(page.locator('#status')).toHaveText('HTTP 201');
  await expect(page.locator('#copy-response')).toBeEnabled();
  await expect(page.locator('#input')).not.toHaveAttribute('readonly');
});

test('browser 404 has accessible recovery links and shared navigation', async ({ page }) => {
  for (const width of [320, 390, 768, 1440, 1600]) {
    await page.setViewportSize({ width, height: 900 });
    const response = await page.goto('/missing-page');
    expect(response.status()).toBe(404);
    await expect(page.getByRole('heading', { name: 'Page not found.' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(audit.violations).toEqual([]);
    await page.screenshot({ path: `test-results/404-${width}.png`, fullPage: true });
  }
  await page.getByRole('link', { name: 'Open playground', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole('link', { name: 'Engines', exact: true }).click();
  await expect(page.locator('.header [aria-current="location"]')).toHaveText('Engines');
  await page.getByRole('link', { name: 'API docs', exact: true }).click();
  await expect(page.locator('.header [aria-current="page"]')).toHaveText('API docs');
});

test('production static pages render with local assets and real proxied API responses', async ({ page }) => {
  // Emulate only the hosting rewrite; the response comes from the real local API.
  await page.route('http://127.0.0.1:3127/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/health' || path === '/openapi.json' || path.startsWith('/models')) {
      const response = await route.fetch({ url: `http://127.0.0.1:3125${path}` });
      await route.fulfill({ response });
    } else await route.continue();
  });
  await page.goto('http://127.0.0.1:3127/');
  await page.locator('#run').click();
  await expect(page.locator('#status')).toHaveText('HTTP 201');
  for (const path of ['/docs', '/redoc']) {
    await page.goto(`http://127.0.0.1:3127${path}/`);
    await expect(page.locator('#docs-feedback')).toBeHidden({ timeout: 35000 });
    await expect(page.locator('.docs-tabs [aria-current="page"]')).toHaveAttribute('href', path);
    await expect(page.locator('#api-reference')).toContainText('Register, list, inspect and delete models.');
  }
});
