# Публикация следующих версий

Обычный путь: изменить VERSION/CHANGELOG, сохранить проверенные изменения в main. Workflow `Publish version` проверит структуру и тесты, создаст новый тег, релиз и ZIP из точного публикуемого коммита. Старые релизы не перезаписываются. Проверить успешность обоих workflows, совпадение тега с исходниками и наличие архива. При ошибке выпуска не называть версию опубликованной. Ручной путь ниже — альтернатива, его не запускать одновременно с автоматическим выпуском.

Репозиторий уже существует и приватный. Нужны git и авторизованный GitHub CLI с правом записи либо доступный GitHub-коннектор для атомарного обновления файлов. Работать от текущего удалённого состояния, чтобы не перезаписать изменения других сопровождающих. Пример для v0.4.0; заменять версию при следующем выпуске. Существующие теги и архивы не перезаписывать. При публикации через коннектор использовать текущий tree как основу и проверку ожидаемого head при обновлении ветки; не подменять удалённую историю локальным расходящимся клоном.

```sh
python3 tests/validate_structure.py
python3 -m unittest discover -s tests -v
git add .
git commit -m "Make the radar personal with verified Russian events and survey handoff"
git push origin main
git tag v0.4.0
git push origin v0.4.0
mkdir -p dist
git archive --format=zip --prefix=vitech-events-radar/ HEAD -o dist/vitech-events-radar-v0.4.0.zip
gh release create v0.4.0 dist/vitech-events-radar-v0.4.0.zip --title "Vi.Tech Events Radar v0.4.0" --notes-file CHANGELOG.md
```

Сотрудникам нужен read-доступ через Settings → Collaborators либо переданный ZIP. Размещение в организации — отдельное решение владельца. Не менять доступ и настройки других репозиториев.
