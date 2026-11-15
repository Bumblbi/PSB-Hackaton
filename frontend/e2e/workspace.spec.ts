import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { randomUUID } from 'node:crypto';

test.beforeEach(async ({ page }) => {
  const response = await page.request.post('/api/v1/auth/register', {
    headers: { 'X-Requested-With': 'legal-workspace' },
    data: {
      name: 'Тестовый юрист',
      email: `workspace.${randomUUID()}@example.com`,
      password: 'test password phrase 2026',
    },
  });
  expect(response.status()).toBe(201);
});

async function ask(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Уточнить контекст' }).click();
  await page.getByLabel('Дата события', { exact: true }).fill('2024-01-01');
  await page
    .getByLabel('Юридический вопрос', { exact: true })
    .fill('Какой срок оплаты по договору сопровождения?');
  await page.getByRole('button', { name: 'Отправить вопрос' }).click();
  await expect(page.getByText('Ответ с основаниями', { exact: true })).toBeVisible();
}

test('creates a chat, checks the exact source and restores saved history', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await ask(page);
  await expect(page.getByRole('article', { name: 'Ответ ассистента' })).toContainText(
    '10 рабочих дней',
  );
  const address = page.url();
  await page.getByRole('button', { name: 'Открыть источник 1', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('Источник [1]', { exact: true })).toBeVisible();
  await expect(dialog.locator('mark')).toContainText('10 рабочих дней');
  await expect(dialog.getByText('Редакция demo-1')).toBeVisible();
  await dialog.getByRole('tab', { name: 'Только фрагмент' }).click();
  await expect(dialog.locator('.source-section')).toHaveCount(1);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Открыть источник 1', exact: true })).toBeFocused();
  await page.reload();
  await expect(page.getByText('Ответ с основаниями', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(address);
  await expect(page.getByLabel('Юридический вопрос')).toHaveValue('');
  await page.getByRole('button', { name: 'Новый диалог', exact: false }).click();
  await expect(page.getByRole('heading', { name: 'Новый диалог' })).toBeVisible();
  await page.locator('.history-item').filter({ hasText: 'Какой срок оплаты' }).first().click();
  await expect(page.getByText('Ответ с основаниями', { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test('searches documents, clears empty results and scopes a question to a document', async ({
  page,
}) => {
  await page.goto('/#/documents');
  await expect(page.locator('.document-row')).toHaveCount(2);
  await page.getByLabel('Поиск документов').fill('несуществующий');
  await expect(page.getByRole('heading', { name: 'Документы не найдены' })).toBeVisible();
  await page.getByRole('button', { name: 'Сбросить фильтры' }).click();
  await page.getByLabel('Тип документа', { exact: true }).selectOption('contract');
  await expect(page.locator('.document-row')).toHaveCount(1);
  await page.locator('.document-row').click();
  await expect(page.getByRole('dialog').getByText('Редакция demo-1')).toBeVisible();
  await page.getByRole('button', { name: 'Вопрос по документу' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.context-tags')).toContainText('Договор сопровождения');
  await expect(page.getByLabel('Юридический вопрос')).toBeFocused();
  await page.getByRole('button', { name: 'Убрать документ из контекста' }).click();
  await expect(page.locator('.context-tags')).toHaveCount(0);
});

test('keeps the draft and rolls back messages when the provider fails', async ({ page }) => {
  await page.route('**/api/v1/chats/*/messages', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'LLM недоступна' }),
    }),
  );
  await page.goto('/');
  const question = 'Какой срок оплаты по договору?';
  await page.getByLabel('Юридический вопрос').fill(question);
  await page.getByRole('button', { name: 'Отправить вопрос' }).click();
  await expect(page.getByRole('alert')).toContainText('Модель сейчас недоступна');
  await expect(page.getByLabel('Юридический вопрос')).toHaveValue(question);
  await expect(page.locator('.user-message')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Отправить вопрос' })).toBeEnabled();
});

test('prevents duplicate submissions and sends date and type filters', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Уточнить контекст' }).click();
  await page.getByLabel('Дата события', { exact: true }).fill('2024-01-01');
  await page.getByLabel('Тип документа', { exact: true }).selectOption('contract');
  let count = 0;
  await page.route('**/api/v1/chats/*/messages', async (route) => {
    count++;
    expect(route.request().postDataJSON()).toEqual({
      question: 'Срок оплаты',
      event_date: '2024-01-01',
      document_kind: 'contract',
    });
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.continue();
  });
  await page.getByLabel('Юридический вопрос').fill('Срок оплаты');
  await page.getByRole('button', { name: 'Отправить вопрос' }).click();
  await expect(page.getByRole('button', { name: 'Отправить вопрос' })).toBeDisabled();
  await expect(page.getByText('Ответ с основаниями', { exact: true })).toBeVisible();
  expect(count).toBe(1);
});

test('shows an unavailable history and supports recovery', async ({ page }) => {
  await page.route('**/api/v1/chats?*', (route) => route.fulfill({ status: 503, body: '{}' }));
  await page.goto('/');
  await expect(page.getByText('История недоступна', { exact: false })).toBeVisible();
  await page.unroute('**/api/v1/chats?*');
  await page.getByRole('button', { name: 'Повторить загрузку' }).click();
  await expect(page.getByText('История недоступна', { exact: false })).toHaveCount(0);
});

test('handles a missing chat and does not send to an invalid route', async ({ page }) => {
  await page.goto('/#/chat/00000000-0000-0000-0000-000000000000');
  await expect(page.getByRole('heading', { name: 'Диалог не загрузился' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Отправить вопрос' })).toBeDisabled();
});

test('supports a narrow viewport and accessible source navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Открыть меню' }).click();
  await page.getByRole('button', { name: 'Документы', exact: false }).click();
  await expect(page.getByRole('heading', { name: 'Документы и редакции' })).toBeVisible();
  await page.locator('.document-row').first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const accessibility = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);
  await page.getByRole('button', { name: 'Закрыть документ' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('meets accessibility checks for the work area and answer', async ({ page }) => {
  await page.goto('/');
  const empty = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(empty.violations).toEqual([]);
  await ask(page);
  const answered = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .analyze();
  expect(answered.violations).toEqual([]);
});

test('captures three review views', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await expect(page.getByText('Корпус подключён', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/review-workspace.png' });
  await ask(page);
  await page.getByRole('button', { name: 'Открыть источник 1', exact: true }).click();
  await expect(page.getByRole('dialog').locator('mark')).toBeVisible();
  await page.screenshot({ path: 'test-results/review-evidence.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/review-mobile.png' });
});

test('opens the context and highlights a date rejected by the server', async ({ page }) => {
  await page.route('**/api/v1/chats/*/messages', (route) =>
    route.fulfill({
      status: 422,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: 'Исправьте указанные поля',
        errors: [
          {
            field: 'event_date',
            message: 'Укажите дату события в формате ГГГГ-ММ-ДД',
          },
        ],
      }),
    }),
  );
  await page.goto('/');
  await page.getByLabel('Юридический вопрос').fill('Срок оплаты по договору');
  await page.getByRole('button', { name: 'Отправить вопрос' }).click();
  await expect(page.getByLabel('Дата события', { exact: true })).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  await expect(page.getByLabel('Дата события', { exact: true })).toBeFocused();
  await expect(page.locator('#composer-event_date-error')).toContainText('ГГГГ-ММ-ДД');
  await expect(page.getByRole('alert')).not.toContainText('выбранный документ');
  await expect(page.getByLabel('Юридический вопрос')).toHaveValue('Срок оплаты по договору');
  await page.getByLabel('Дата события', { exact: true }).fill('2024-01-01');
  await expect(page.locator('#composer-event_date-error')).toHaveCount(0);
});
