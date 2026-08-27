## STATUS.md — обновлено 25.08.2026, сессия S3

### Закрыто
- ADR-038 реализован полностью. Прогон: 3 failed, 144 passed,
  mypy Success (59 files). Три падения — те же, что были ДО сессии
  (test_real_components.py: два на хардкод размера каталога,
  один на удалённый generator_lifan_lf2800i_2 — решено оставить
  как есть, не приоритет). Новых падений нет.
- Новые файлы: catalog/sources_loader.py, api/display_index.py,
  data/sources.yaml (17 доменов), tests/test_display_index.py.
- Контракт наполнен: RecommendationOut.purchases (len 1 или 2),
  capacity_source, solar_optional. Роль в ките — по позиции
  в component_offer_ids, парсинг offer_id нигде не используется.
- image_url = None у всех позиций. Это не ошибка загрузки (ADR-038),
  own-hosted картинки — задача данных, S8.
- Закоммичено и запушено: df14610, origin/main == HEAD (проверено
  git fetch + git log).

### Не сделано (сознательно, вне слоя)
- В README.md ADR-038 содержит неточность: сказано, что
  InverterSpec живёт в core/solution.py и это «единственное
  пересечение с core/». Фактически InverterSpec — в
  catalog/components.py, слой core/ в ADR-038 не затронут вообще.
  Текст ADR не правился (правило: ADR целыми блоками), исправить
  отдельно.
- venv/ по-прежнему не в .gitignore.
- CLAUDE.md — untracked, решение о коммите не принято.

### Первое, что проверить в следующей сессии
- S4 (шаблон карточки) разблокирован: RecommendationOut содержит
  всё для рендера, кроме картинок.
- Шаблон читает только RecommendationOut. Если понадобится поле,
  которого нет — это повод вернуться к ADR, не обходить границу.
- Для китов в шаблоне: две кнопки по purchases[0]/purchases[1],
  текст «сонячні панелі не обов'язкові» при solar_optional is True.