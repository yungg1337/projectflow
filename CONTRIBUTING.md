# Как работать с проектом

1. Ветки: `main` — готовый код, `develop` — сборка, `feature/*` — отдельная задача.
2. Сообщения коммитов — по схеме Conventional Commits: `feat(tasks): добавил фильтр по статусу`.
3. Перед отправкой изменений выполнить:
   ```bash
   python tools/check.py
   python -m unittest discover -s tests -t .
   ```
4. Новые возможности сопровождать тестами и дописывать в `CHANGELOG.md`.
