import { ApiError } from '../api';

export type FieldErrors = Record<string, string>;

export function errorsByField(error: unknown): FieldErrors {
  return error instanceof ApiError
    ? Object.fromEntries(error.errors.map((item) => [item.field, item.message]))
    : {};
}

export function focusFirstError(form: HTMLFormElement, errors: FieldErrors) {
  for (const element of Array.from(form.elements)) {
    const field = element.getAttribute('name');
    if (field && errors[field] && element instanceof HTMLElement) {
      element.focus();
      return true;
    }
  }
  return false;
}

export function fieldAccessibility(errors: FieldErrors, field: string, prefix: string) {
  return {
    'aria-invalid': errors[field] ? true : undefined,
    'aria-describedby': errors[field] ? `${prefix}-${field}-error` : undefined,
  };
}

export default function FieldError({
  errors,
  field,
  prefix,
}: {
  errors: FieldErrors;
  field: string;
  prefix: string;
}) {
  return errors[field] ? (
    <span className="field-error" id={`${prefix}-${field}-error`}>
      {errors[field]}
    </span>
  ) : null;
}
