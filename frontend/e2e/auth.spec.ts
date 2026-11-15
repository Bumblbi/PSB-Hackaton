import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { randomUUID } from 'node:crypto';

const password = 'a long local password phrase 2026';
async function register(page: Page, email: string) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Создать учётную запись', exact: true }).click();
  await page.getByLabel('Имя', { exact: true }).fill('Локальный юрист');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.getByLabel('Повторите пароль', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Зарегистрироваться', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Новый диалог', exact: true })).toBeVisible();
}

test('registers, restores the session, logs out and changes the password', async ({ page }) => {
  const email = `auth.${randomUUID()}@example.com`;
  await register(page, email);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Новый диалог', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.cookie.includes('legal_session'))).toBe(false);
  expect(await page.evaluate(() => localStorage.length)).toBe(0);
  await page.getByRole('button', { name: 'Выйти', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Войти в рабочее место' })).toBeVisible();
  expect((await page.request.get('/api/v1/chats')).status()).toBe(401);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await page.getByRole('button', { name: 'Изменить пароль' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Текущий пароль', { exact: true }).fill(password);
  await dialog.getByLabel('Новый пароль', { exact: true }).fill(password + ' new');
  await dialog.getByLabel('Повторите новый пароль', { exact: true }).fill(password + ' new');
  await dialog.getByRole('button', { name: 'Сохранить пароль' }).click();
  await expect(page.getByText('Пароль изменён. Войдите с новым паролем')).toBeVisible();
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Неверный email или пароль');
  await page.getByLabel('Пароль', { exact: true }).fill(password + ' new');
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Новый диалог', exact: true })).toBeVisible();
});

test('does not expose a private chat to another browser session', async ({ page, browser }) => {
  await register(page, `owner.${randomUUID()}@example.com`);
  await page.getByLabel('Юридический вопрос').fill('Срок оплаты по договору');
  await page.getByRole('button', { name: 'Отправить вопрос' }).click();
  await expect(page.getByText('Ответ с основаниями', { exact: true })).toBeVisible();
  const privateUrl = page.url();
  const other = await browser.newContext();
  try {
    const otherPage = await other.newPage();
    await register(otherPage, `other.${randomUUID()}@example.com`);
    await otherPage.goto(privateUrl);
    await expect(otherPage.getByRole('heading', { name: 'Диалог не загрузился' })).toBeVisible();
    await expect(otherPage.getByText('Ответ с основаниями', { exact: true })).toHaveCount(0);
  } finally {
    await other.close();
  }
});

test('validates password confirmation and renders an accessible registration form', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Создать учётную запись', exact: true }).click();
  await page.getByLabel('Имя', { exact: true }).fill('Юрист');
  await page.getByLabel('Email', { exact: true }).fill(`validation.${randomUUID()}@example.com`);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.getByLabel('Повторите пароль', { exact: true }).fill('different');
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click();
  await expect(page.getByRole('alert')).toContainText('Пароли не совпадают');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({ path: 'test-results/auth-mobile.png' });
});

test('shows every server field error and registers immediately after corrections', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Создать учётную запись', exact: true }).click();
  await page.getByLabel('Имя', { exact: true }).fill('   ');
  await page.getByLabel('Email', { exact: true }).fill('invalid-email');
  await page.getByLabel('Пароль', { exact: true }).fill('short');
  await page.getByLabel('Повторите пароль', { exact: true }).fill('short');
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click();
  await expect(page.getByLabel('Имя', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByLabel('Email', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByLabel('Пароль', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  await expect(page.locator('#auth-email-error')).toContainText('name@example.ru');
  await expect(page.locator('#auth-password-error')).toContainText('15');
  await expect(page.getByLabel('Имя', { exact: true })).toBeFocused();
  expect(
    (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({ path: 'test-results/registration-field-errors.png' });
  await page.getByLabel('Имя', { exact: true }).fill('Юрист');
  await expect(page.locator('#auth-name-error')).toHaveCount(0);
  await expect(page.locator('#auth-email-error')).toBeVisible();
  await page.getByLabel('Email', { exact: true }).fill(`fields.${randomUUID()}@example.com`);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.getByLabel('Повторите пароль', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click();
  await expect(page.getByRole('heading', { name: 'Новый диалог', exact: true })).toBeVisible();
});

test('marks both fields for incorrect login credentials', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Email', { exact: true }).fill(`missing.${randomUUID()}@example.com`);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Неверный email или пароль');
  await expect(page.getByLabel('Email', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByLabel('Пароль', { exact: true })).toHaveAttribute('aria-invalid', 'true');
  await expect(page.getByLabel('Email', { exact: true })).toBeFocused();
});
