# DriftBench-Offline

Генератор корпуса событий configuration drift для Kubernetes GitOps-окружений.

Проект создан для формирования детерминированного набора данных для сравнительного исследования методов классификации конфигурационного дрейфа (rule-based vs LLM).

## Принципы генератора
- **Детерминизм**: результаты полностью воспроизводимы при фиксированном значении `--seed`.
- **Чистота разметки**: генератор не производит оценок и не присваивает уровней опасности.
- **Offline / Server dry-run**: кластер `kind` используется исключительно для валидации синтаксиса и схемы манифестов через `kubectl apply --dry-run=server`.

---

## Требования
- Python 3.11+
- `helm` (v3+)
- `kind` (v0.20+)
- `kubectl` (v1.28+)
- Docker (Docker Desktop или Linux daemon)

Установка зависимостей Python:
```bash
pip install -r requirements.txt
```

---

## Использование

### Полный цикл генерации корпуса (одной командой)
```bash
python -m driftbench all --seed 42
```
или с сохранением кластера для отладки:
```bash
python -m driftbench all --seed 42 --keep-cluster
```

### Отдельные этапы (подкоманды)
1. **Рендеринг baseline-манифестов**:
   ```bash
   python -m driftbench render
   ```
2. **Генерация кейсов с мутациями**:
   ```bash
   python -m driftbench generate --seed 42 --target-count 330
   ```
3. **Валидация манифестов на kind (server dry-run)**:
   ```bash
   python -m driftbench validate
   ```
4. **Экспорт слепых таблиц и сплитов**:
   ```bash
   python -m driftbench export --seed 42
   ```
5. **Формирование отчета**:
   ```bash
   python -m driftbench report --seed 42
   ```

---

## Запуск тестов
```bash
pytest
```

Набор тестов проверяет:
- Корректность вычисления структурного diff (`tests/test_diff.py`);
- Применимость всех операторов мутаций и соответствие путей (`tests/test_operators.py`);
- Побайтную воспроизводимость генерации (`tests/test_determinism.py`);
- Отсутствие нежелательных маркеров классов в генераторе и аннотациях (`tests/test_static_hygiene.py`).

---

## Структура репозитория
```
driftbench/
  charts.yaml            # список чартов, версии, values
  render.py              # helm template -> baseline-манифесты
  operators/             # каталог операторов мутаций (по областям)
  diff.py                # вычисление структурного diff
  generate.py            # сэмплирование кейсов
  validate.py            # проверка на kind (server dry-run)
  export.py              # таблицы для разметки, сплиты, viewer.html
  report.py              # генерация REPORT.md
tests/                   # автоматические тесты (pytest)
baseline/                # отрендеренные исходные манифесты
dataset/
  raw/                   # сгенерированные кейсы (desired, live, diff, meta)
  rejected/              # кейсы, отклоненные при валидации
  splits/                # operators.json, cases.json
  annotation/            # annotation_main.csv, annotation_second.csv, viewer.html
  index.csv              # полный индекс датасета
  REPORT.md              # детальный отчет
annotated_dataset/       # размеченные таблицы (annotation_main_labeled.csv, annotation_second_labeled.csv)
requirements.txt
README.md
```

## Лицензия

- **Код генератора** (`driftbench/`, `tests/`, `Makefile` и сопутствующие файлы) распространяется по лицензии [MIT](LICENSE).
- **Корпус и разметка** (`dataset/`, `annotated_dataset/`) распространяются по лицензии [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). При использовании необходимо указывать авторство.
- Манифесты в `baseline/` (а также исходные части `desired.yaml` в корпусе) получены рендерингом сторонних Helm-чартов и остаются под лицензиями этих чартов.
