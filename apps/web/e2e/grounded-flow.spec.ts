import { expect, test } from '@playwright/test';
import path from 'node:path';

test('upload, process, ask a grounded question, and open the cited page', async ({ page }) => {
  await page.goto('/documents');
  const sample = path.resolve('../../sample_documents/groundedpdf-sample.pdf');
  await page.locator('input[type=file]').setInputFiles(sample);
  await expect(page.getByText('ready', { exact: true })).toBeVisible({ timeout: 30_000 });

  await page.goto('/chat');
  await page.getByRole('button', { name: 'New conversation' }).first().click();
  await page.getByRole('button', { name: /Select documents/ }).click();
  await page.getByRole('checkbox', { name: /GroundedPDF Evaluation Brief/i }).check();
  await page.keyboard.press('Escape');
  await page.getByLabel('Ask a question').fill('What efficiency gain was measured in the pilot?');
  await page.getByRole('button', { name: 'Send question' }).click();

  await expect(page.getByLabel('assistant message')).toContainText(/37 percent/i, {
    timeout: 30_000,
  });
  await page.getByLabel('Ask a question').fill('What is the orbital speed of Neptune?');
  await page.getByRole('button', { name: 'Send question' }).click();
  await expect(page.getByLabel('assistant message').last()).toContainText(
    "I couldn't find enough evidence in the selected documents to answer that question.",
    { timeout: 30_000 },
  );
  // Sources are collapsed by default; expand the first answer's sources.
  await page.locator('summary', { hasText: 'Sources' }).first().click();
  const citation = page.getByRole('link', { name: /Open groundedpdf-sample.pdf page 2/i });
  await expect(citation).toBeVisible();
  await citation.click();
  // Page-level citation indicators remain the baseline assertion.
  await expect(page.getByText('Cited page 2')).toBeVisible();
  await expect(page.getByLabel('Cited page 2')).toBeVisible();
  await expect(page.getByText(/Pilot Findings/i)).toBeVisible({ timeout: 30_000 });
  // Exact evidence highlighting: the cited passage is wrapped in text-layer marks.
  const highlighted = page.locator('mark.evidence-highlight', { hasText: '37' });
  await expect(highlighted.first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole('link', { name: 'Back to chat' }).click();
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]+$/);
  await expect(page.getByLabel('assistant message').last()).toContainText(/couldn't find enough/i);
});
