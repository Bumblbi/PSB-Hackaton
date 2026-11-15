"""Public field errors, built without echoing submitted values or validator internals."""

from fastapi.responses import JSONResponse

FIELD_MESSAGES = {
    "email": "Введите email в формате name@example.ru",
    "name": "Укажите имя от 1 до 100 символов без переносов строк",
    "password": "Введите пароль от 1 до 128 символов",
    "current_password": "Введите текущий пароль от 1 до 128 символов",
    "new_password": "Новый пароль должен содержать от 15 до 128 символов и не состоять из пробелов",
    "question": "Введите вопрос от 1 до 8000 символов, содержащий текст",
    "event_date": "Укажите дату события в формате ГГГГ-ММ-ДД и проверьте число, месяц и год",
    "document_id": "Выберите документ из библиотеки или уберите его из контекста",
    "document_kind": "Выберите тип документа из списка",
    "history": "История должна содержать не более 20 сообщений пользователя или ассистента",
    "role": "Роль сообщения должна быть user или assistant",
    "content": "Текст сообщения должен содержать от 1 до 16000 символов",
    "title": "Название диалога должно содержать от 1 до 200 символов",
    "corpus_path": "Укажите путь к manifest-файлу длиной от 1 до 500 символов",
    "version_id": "Выберите доступную редакцию документа",
    "chat_id": "Проверьте ссылку на диалог или откройте его из истории",
    "chunk_id": "Откройте фрагмент по ссылке в ответе",
    "q": "Поисковый запрос должен содержать не более 200 символов",
    "kind": "Выберите тип документа из списка",
    "limit": "Размер страницы должен быть целым числом от 1 до 100",
    "offset": "Смещение страницы должно быть целым числом не меньше нуля",
}


class FieldValidationError(Exception):
    def __init__(self, errors: dict[str, str], status_code=422, detail="Исправьте указанные поля"):
        self.errors = errors
        self.status_code = status_code
        self.detail = detail


def field_error_response(errors, status_code=422, detail="Исправьте указанные поля"):
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "errors": [{"field": field, "message": message} for field, message in errors.items()],
        },
    )


def request_field_errors(validation_errors, registration=False):
    result = {}
    for error in validation_errors:
        location = error.get("loc", ())
        parts = location[1:] if location and location[0] in {"body", "query", "path"} else location
        field = parts[0] if parts else "request"
        if field not in FIELD_MESSAGES or error["type"] == "extra_forbidden":
            result["request"] = (
                "Не удалось прочитать данные формы. Обновите страницу и повторите отправку"
            )
            continue
        message = FIELD_MESSAGES[field]
        if field == "password" and registration:
            message = "Пароль должен содержать от 15 до 128 символов и не состоять из пробелов"
        elif field == "password" and error["type"] == "value_error":
            message = "Пароль должен содержать текст и не состоять из пробелов"
        if field == "history" and len(parts) >= 3 and isinstance(parts[1], int):
            nested = parts[2]
            if nested in {"role", "content"}:
                field = f"history.{parts[1]}.{nested}"
                message = f"Сообщение истории {parts[1] + 1}. {FIELD_MESSAGES[nested]}"
        result[field] = message
    return result
