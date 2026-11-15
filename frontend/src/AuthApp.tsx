import { Eye, EyeOff, KeyRound, LogIn, ShieldCheck, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import App from './App';
import { api, ApiError, errorText, setCsrfToken } from './api';
import type { User, UserSession } from './types';
import FieldError, {
  errorsByField,
  fieldAccessibility,
  focusFirstError,
  type FieldErrors,
} from './components/FieldError';

export default function AuthApp() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectionError, setConnectionError] = useState('');
  const [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setConnectionError('');
    api
      .session(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setCsrfToken(result.csrf_token);
          setUser(result.user);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted && !(error instanceof ApiError && error.status === 401))
          setConnectionError(errorText(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    const expired = () => {
      setCsrfToken('');
      setUser(null);
      setPasswordOpen(false);
      setNotice('Сессия завершена. Войдите снова');
    };
    window.addEventListener('auth-expired', expired);
    return () => {
      controller.abort();
      window.removeEventListener('auth-expired', expired);
    };
  }, [attempt]);
  function authenticated(session: UserSession) {
    setCsrfToken(session.csrf_token);
    setUser(session.user);
    setNotice('');
    setLogoutError('');
    window.location.hash = '/new';
  }
  async function logout() {
    try {
      await api.logout();
      setCsrfToken('');
      setUser(null);
      setNotice('Вы вышли из учётной записи');
      window.location.hash = '/new';
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setCsrfToken('');
        setUser(null);
      } else setLogoutError('Выход не выполнен. Проверьте соединение и повторите попытку');
    }
  }
  if (loading)
    return (
      <main className="auth-loading" role="status">
        Открываем рабочее место…
      </main>
    );
  if (connectionError)
    return (
      <main className="auth-loading">
        <h1>Нет соединения с сервером</h1>
        <p role="alert">{connectionError}</p>
        <button className="primary-button" onClick={() => setAttempt((n) => n + 1)}>
          Повторить подключение
        </button>
      </main>
    );
  if (!user) return <AuthForm notice={notice} onAuthenticated={authenticated} />;
  return (
    <>
      {logoutError && (
        <div className="account-error" role="alert">
          {logoutError}
          <button onClick={() => void logout()}>Повторить выход</button>
        </div>
      )}
      <App
        key={user.id}
        user={user}
        onLogout={() => void logout()}
        onPassword={() => setPasswordOpen(true)}
      />
      {passwordOpen && (
        <PasswordDialog
          onClose={() => setPasswordOpen(false)}
          onChanged={() => {
            setPasswordOpen(false);
            setCsrfToken('');
            setUser(null);
            setNotice('Пароль изменён. Войдите с новым паролем');
          }}
        />
      )}
    </>
  );
}

function AuthForm({
  notice,
  onAuthenticated,
}: {
  notice: string;
  onAuthenticated: (session: UserSession) => void;
}) {
  const [register, setRegister] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  function clearField(field: string) {
    setFieldErrors((previous) => {
      const next = { ...previous };
      delete next[field];
      return next;
    });
    setError('');
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget as HTMLFormElement;
    if (register && password !== confirmation) {
      setError('Пароли не совпадают');
      setFieldErrors({ confirmation: 'Повторите тот же пароль, который указан выше' });
      focusFirstError(form, { confirmation: 'Пароли не совпадают' });
      return;
    }
    setBusy(true);
    setError('');
    setFieldErrors({});
    try {
      onAuthenticated(
        await (register
          ? api.register(name.trim(), email.trim(), password)
          : api.login(email.trim(), password)),
      );
    } catch (error) {
      setError(errorText(error));
      const fields = errorsByField(error);
      setFieldErrors(fields);
      window.requestAnimationFrame(() => focusFirstError(form, fields));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <section className="auth-brand">
        <div className="brand-wordmark">
          ПСБ
          <span className="brand-rule" />
        </div>
        <div>
          <span className="eyebrow">Юридический ассистент</span>
          <h1>
            Работа с документами.
            <br />
            Основания для решений.
          </h1>
          <p>Задавайте вопросы по корпусу и проверяйте выводы по цитатам из конкретных редакций</p>
        </div>
        <div className="auth-brand-footer">
          <ShieldCheck />
          Личные диалоги и проверяемые источники
        </div>
      </section>
      <section className="auth-form-area" aria-labelledby="auth-title">
        <div className="auth-card">
          <div className="auth-icon">
            <LogIn />
          </div>
          <h2 id="auth-title">{register ? 'Создать учётную запись' : 'Войти в рабочее место'}</h2>
          <p className="auth-subtitle">
            {register
              ? 'Имя и email будут использоваться в вашем профиле'
              : 'Продолжите работу со своими диалогами'}
          </p>
          {notice && (
            <p className="auth-notice" role="status">
              {notice}
            </p>
          )}
          <form onSubmit={submit} noValidate>
            {register && (
              <label>
                Имя
                <input
                  name="name"
                  aria-label="Имя"
                  autoComplete="name"
                  value={name}
                  maxLength={100}
                  required
                  disabled={busy}
                  {...fieldAccessibility(fieldErrors, 'name', 'auth')}
                  onChange={(e) => {
                    setName(e.target.value);
                    clearField('name');
                  }}
                />
                <FieldError errors={fieldErrors} field="name" prefix="auth" />
              </label>
            )}
            <label>
              Email
              <input
                name="email"
                aria-label="Email"
                type="email"
                autoComplete="username"
                value={email}
                maxLength={254}
                required
                disabled={busy}
                {...fieldAccessibility(fieldErrors, 'email', 'auth')}
                onChange={(e) => {
                  setEmail(e.target.value);
                  clearField('email');
                }}
              />
              <FieldError errors={fieldErrors} field="email" prefix="auth" />
            </label>
            <label htmlFor="auth-password">Пароль</label>
            <div className="password-field">
              <input
                id="auth-password"
                name="password"
                type={visible ? 'text' : 'password'}
                autoComplete={register ? 'new-password' : 'current-password'}
                value={password}
                minLength={register ? 15 : 1}
                maxLength={128}
                required
                disabled={busy}
                {...fieldAccessibility(fieldErrors, 'password', 'auth')}
                aria-describedby={
                  fieldErrors.password
                    ? 'auth-password-error'
                    : register
                      ? 'password-policy'
                      : undefined
                }
                onChange={(e) => {
                  setPassword(e.target.value);
                  clearField('password');
                  clearField('confirmation');
                }}
              />
              <button
                type="button"
                aria-label={visible ? 'Скрыть пароль' : 'Показать пароль'}
                onClick={() => setVisible((v) => !v)}
              >
                {visible ? <EyeOff /> : <Eye />}
              </button>
            </div>
            <FieldError errors={fieldErrors} field="password" prefix="auth" />
            {register && (
              <>
                <p id="password-policy" className="password-policy">
                  От 15 до 128 символов. Можно использовать длинную парольную фразу
                </p>
                <label>
                  Повторите пароль
                  <input
                    name="confirmation"
                    aria-label="Повторите пароль"
                    type="password"
                    autoComplete="new-password"
                    value={confirmation}
                    maxLength={128}
                    required
                    disabled={busy}
                    {...fieldAccessibility(fieldErrors, 'confirmation', 'auth')}
                    onChange={(e) => {
                      setConfirmation(e.target.value);
                      clearField('confirmation');
                    }}
                  />
                  <FieldError errors={fieldErrors} field="confirmation" prefix="auth" />
                </label>
              </>
            )}
            {error && (
              <p className="auth-error" role="alert">
                {error}
              </p>
            )}
            <button className="primary-button auth-submit" type="submit" disabled={busy}>
              {busy ? 'Подождите…' : register ? 'Зарегистрироваться' : 'Войти'}
            </button>
          </form>
          <p className="auth-switch">
            {register ? 'Уже есть учётная запись?' : 'Первый вход?'}
            <button
              disabled={busy}
              onClick={() => {
                setRegister((v) => !v);
                setPassword('');
                setConfirmation('');
                setVisible(false);
                setError('');
                setFieldErrors({});
              }}
            >
              {register ? 'Войти' : 'Создать учётную запись'}
            </button>
          </p>
        </div>
      </section>
    </main>
  );
}

function PasswordDialog({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  function clearField(field: string) {
    setFieldErrors((previous) => {
      const updated = { ...previous };
      delete updated[field];
      return updated;
    });
    setError('');
  }
  useEffect(() => {
    const element = ref.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget as HTMLFormElement;
    if (next !== confirmation) {
      setError('Пароли не совпадают');
      setFieldErrors({ confirmation: 'Повторите тот же новый пароль' });
      focusFirstError(form, { confirmation: 'Пароли не совпадают' });
      return;
    }
    setBusy(true);
    setError('');
    setFieldErrors({});
    try {
      await api.changePassword(current, next);
      onChanged();
    } catch (error) {
      setError(errorText(error));
      const fields = errorsByField(error);
      setFieldErrors(fields);
      window.requestAnimationFrame(() => focusFirstError(form, fields));
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={ref}
      className="help-dialog password-dialog"
      aria-labelledby="password-title"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else onClose();
      }}
    >
      <div>
        <header>
          <h2 id="password-title">Изменить пароль</h2>
          <button
            className="icon-button"
            aria-label="Закрыть смену пароля"
            disabled={busy}
            onClick={onClose}
          >
            <X />
          </button>
        </header>
        <p>После изменения все сеансы этой учётной записи завершатся</p>
        <form onSubmit={submit} noValidate>
          <label>
            Текущий пароль
            <input
              type="password"
              name="current_password"
              aria-label="Текущий пароль"
              autoComplete="current-password"
              value={current}
              maxLength={128}
              required
              disabled={busy}
              {...fieldAccessibility(fieldErrors, 'current_password', 'change')}
              onChange={(e) => {
                setCurrent(e.target.value);
                clearField('current_password');
              }}
            />
            <FieldError errors={fieldErrors} field="current_password" prefix="change" />
          </label>
          <label>
            Новый пароль
            <input
              type="password"
              name="new_password"
              aria-label="Новый пароль"
              autoComplete="new-password"
              value={next}
              minLength={15}
              maxLength={128}
              required
              disabled={busy}
              {...fieldAccessibility(fieldErrors, 'new_password', 'change')}
              onChange={(e) => {
                setNext(e.target.value);
                clearField('new_password');
                clearField('confirmation');
              }}
            />
            <FieldError errors={fieldErrors} field="new_password" prefix="change" />
          </label>
          <label>
            Повторите новый пароль
            <input
              type="password"
              name="confirmation"
              aria-label="Повторите новый пароль"
              autoComplete="new-password"
              value={confirmation}
              maxLength={128}
              required
              disabled={busy}
              {...fieldAccessibility(fieldErrors, 'confirmation', 'change')}
              onChange={(e) => {
                setConfirmation(e.target.value);
                clearField('confirmation');
              }}
            />
            <FieldError errors={fieldErrors} field="confirmation" prefix="change" />
          </label>
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}
          <button className="primary-button" disabled={busy}>
            <KeyRound />
            {busy ? 'Сохраняем…' : 'Сохранить пароль'}
          </button>
        </form>
      </div>
    </dialog>
  );
}
