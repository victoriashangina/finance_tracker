# Как загрузить проект на GitHub

Команды выполняй в Терминале по одной. Git в этой папке первоначально не был инициализирован. Если уже выполнила часть шагов, продолжай с нужного места, не создавая второй репозиторий.

## 1. Создай пустой репозиторий

Открой https://github.com/new. Имя — например `potok`. Выбери Public, если преподаватель должен открыть код без приглашения, или Private для закрытого доступа. Не добавляй README, .gitignore и лицензию на этом шаге: в локальном проекте уже есть README и .gitignore. Нажми Create repository.

## 2. Перейди в папку исходного кода

```sh
cd "/Users/victoriashangina/Documents/Codex/2026-11-08/new-chat/outputs/finance_tracker"
```

Именно здесь находится `manage.py`. Не загружай всю папку `new-chat`: в ней есть другие учебные документы и рабочие файлы.

## 3. Создай локальный Git-репозиторий

```sh
git init
```

```sh
git branch -M main
```

```sh
git add .
```

```sh
git status
```

Проверь список: должны присутствовать исходники, шаблоны, static, миграции, samples, README, requirements и конфигурация запуска. Не должно быть `.env`, `.local-secret`, `db.sqlite3`, `.venv` и личных банковских выписок. Первые четыре исключены готовым `.gitignore`. `.env.example` загружать нужно: он содержит пустые поля и пример настроек.

```sh
git commit -m "Initial version of Potok"
```

Если Git сообщает `Author identity unknown`, выполни `git config user.name "Твоё имя"` и `git config user.email "Твоя почта GitHub"`, затем повтори commit. Для публичных коммитов можно взять скрывающий почту адрес из GitHub → Settings → Emails. Это настройки только данного репозитория, без `--global`.

## 4. Подключи GitHub и отправь файлы

Скопируй HTTPS-адрес своего репозитория. В следующей команде замени `YOUR_LOGIN` и, если нужно, имя `potok`:

```sh
git remote add origin https://github.com/YOUR_LOGIN/potok.git
```

```sh
git push -u origin main
```

Если вход уже настроен, файлы отправятся. Обычный пароль GitHub для Git по HTTPS не используется: потребуется настроенная авторизация через GitHub CLI/менеджер учётных данных, персональный токен или SSH. Секреты вводи только в предназначенный для них запрос, не вставляй токен в URL репозитория или исходный код.

При установленном `gh` можно заранее выполнить `gh auth login`, выбрать GitHub.com → HTTPS → вход в браузере и согласиться настроить авторизацию Git. Если `gh` не установлен, воспользуйся GitHub Desktop либо официальной инструкцией авторизации; установка дополнительных инструментов для уже настроенного Git не обязательна.

После успешной отправки обнови страницу репозитория. В корне должны быть `manage.py`, `README.md`, `requirements.lock.txt`, папки `finance`, `config`, `templates`, `static` и остальные файлы проекта.

## 5. Последующие изменения

Из этой же папки:

```sh
git status
```

```sh
git add .
```

```sh
git commit -m "Describe your changes"
```

```sh
git push
```

`git init` и `git remote add origin` повторять не нужно. Если появилась ошибка `remote origin already exists`, сначала проверь адрес командой `git remote -v`. Не используй `push --force` для исправления обычной ошибки отправки.

## Если загружать через сайт

Из чистого архива проекта можно загрузить распакованное содержимое через **uploading an existing file** или **Add file → Upload files**. Загружай содержимое папки `finance_tracker`, чтобы `manage.py` оказался в корне репозитория. Покажи скрытые файлы в Finder сочетанием Command+Shift+точка: нужны `.gitignore`, `.env.example`, `.dockerignore`, `.python-version`.

При ручной загрузке через сайт `.gitignore` не фильтрует выбранные файлы. Не перетаскивай рабочую папку вместе с базой данных и локальными секретами. Git через терминал удобнее для повторных обновлений и сохранения полной структуры.

GitHub хранит код. Для работающего сайта с регистрацией и базой данных выполни [инструкцию размещения](DEPLOY.md).

Официальный источник: [Adding locally hosted code to GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).
