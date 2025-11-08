import { expect, test } from '@playwright/test';

test.describe('Smoke Capture UI shell', () => {
  test('renders toolbar + tabs', async ({ page, baseURL }) => {
    const target = baseURL ?? 'http://localhost:8000';
    await page.goto(target, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('textbox', { name: /url/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /run/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /rendered markdown/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /raw markdown/i })).toBeVisible();
  });
});
