# Отчет о генерации корпуса DriftBench-Offline

## 1. Среда и версии инструментов

- **Seed**: `42`
- **Git commit**: `44030bb054d7636a95d8825e3a6d74d151021c8e`
- **Helm**: `v4.3.1+gc0d08d0`
- **Kind**: `kind v0.33.0 go1.26.7 windows/amd64`
- **Kubectl** (`kubectl version --client`):
```
Client Version: v1.32.2
Kustomize Version: v5.5.0
```
- **Статус тестов pytest**: `18 passed in 10.47s`

### Зафиксированные версии Helm-чартов и версионные теги образов

| Приложение | Репозиторий / Чарт | Версия чарта | Закрепленный образ/тег | SHA256 архива |
|---|---|---|---|---|
| ingress-nginx | `ingress-nginx/ingress-nginx` | `4.15.1` | `controller:v1.12.0` | `3eff0bd18151d6e6...` |
| kube-state-metrics | `prometheus-community/kube-state-metrics` | `8.6.0` | `kube-state-metrics:v2.15.0` | `9bdf8485c0df29eb...` |
| nginx | `bitnami/nginx` | `25.2.5` | `nginx:1.31.7` | `8a8ed5f09fe591ae...` |
| postgresql | `bitnami/postgresql` | `18.12.14` | `postgresql:18.6.0` | `4fc5b42233e94bd3...` |
| prometheus-node-exporter | `prometheus-community/prometheus-node-exporter` | `4.60.0` | `node-exporter:v1.12.1` | `676c47bb898d0626...` |
| rabbitmq | `bitnami/rabbitmq` | `16.0.14` | `rabbitmq:4.1.3` | `df625220cafdfe89...` |
| redis | `bitnami/redis` | `28.3.1` | `redis:8.10.2` | `4dacf5a4f67aca6d...` |

## 2. Итоги генерации и валидации

- **Сгенерировано кейсов-кандидатов**: `330`
- **Прошло локальную самопроверку (roundtrip YAML + diff)**: `330` (100% кандидатов, поступивших на валидацию)
- **Отброшено генератором на этапе самопроверки**: `14` кандидатов (заменены альтернативными валидными комбинациями)
  * touches unintended path: 10
  * Pair diff mismatch after env normalization: 3
  * Diff is empty: 1
- **Результат применения baseline-манифестов в кластер**: `100%` (126 манифестов применились без ошибок, `0` отказов)
- **Принято валидацией на kind (server dry-run)**: `322`
- **Отклонено валидацией на kind**: `8`

## 3. Распределения в корпусе принятых кейсов

### 3.1 Распределение по типу кейса

| Тип кейса | Количество | Доля |
|---|---|---|
| `single` | 163 | 50.6% |
| `paired` | 96 | 29.8% |
| `compound` | 63 | 19.6% |

### 3.2 Распределение по окружению (Environment)

| Окружение | Количество | Доля |
|---|---|---|
| `prod` | 162 | 50.3% |
| `dev` | 160 | 49.7% |

### 3.3 Распределение по видам ресурсов (Resource Kind)

| Вид ресурса | Количество кейсов |
|---|---|
| `StatefulSet` | 75 |
| `Deployment` | 70 |
| `Service` | 21 |
| `NetworkPolicy` | 20 |
| `DaemonSet` | 18 |
| `Ingress` | 18 |
| `PodDisruptionBudget` | 16 |
| `ConfigMap` | 16 |
| `Secret` | 13 |
| `ServiceAccount` | 10 |
| `Role` | 10 |
| `CronJob` | 9 |
| `ClusterRole` | 8 |
| `HorizontalPodAutoscaler` | 8 |
| `ClusterRoleBinding` | 4 |
| `PersistentVolumeClaim` | 2 |
| `RoleBinding` | 2 |
| `IngressClass` | 2 |

### 3.4 Распределение по приложениям (Charts / Apps)

| Приложение | Количество кейсов |
|---|---|
| `redis` | 66 |
| `nginx` | 64 |
| `postgresql` | 61 |
| `ingress-nginx` | 46 |
| `kube-state-metrics` | 34 |
| `rabbitmq` | 29 |
| `prometheus-node-exporter` | 22 |

### 3.5 Распределение по областям изменений (Areas)

| Область изменений | Вхождений операторов |
|---|---|
| `config` | 51 |
| `metadata` | 80 |
| `network` | 53 |
| `pod_spec` | 37 |
| `rbac` | 24 |
| `resources` | 17 |
| `scaling` | 22 |
| `security_context` | 42 |
| `workload` | 65 |

### 3.6 Распределение по сплитам

| Сплит | Количество кейсов | Доля |
|---|---|---|
| `dev` | 70 | 21.7% |
| `test` | 252 | 78.3% |

### 3.7 Таблица встречаемости операторов мутаций

| Оператор | Принято | Отклонено | Типичная ошибка валидации |
|---|---|---|---|
| `MUT-CFG-CM-ADD` | 9 | 0 | `—` |
| `MUT-CFG-CM-CHANGE` | 7 | 0 | `—` |
| `MUT-CFG-ENV-ADD` | 12 | 0 | `—` |
| `MUT-CFG-ENV-CHANGE` | 4 | 0 | `—` |
| `MUT-CFG-ENV-REMOVE` | 4 | 1 | `The Deployment "ingress-nginx-dev-controller" is invalid: spec.strategy.rolli...` |
| `MUT-CFG-SECRET-CHANGE` | 11 | 0 | `—` |
| `MUT-CFG-SECRETREF-CHANGE` | 4 | 0 | `—` |
| `MUT-ING-ANNOT` | 7 | 0 | `—` |
| `MUT-ING-HOST` | 5 | 0 | `—` |
| `MUT-ING-PATH` | 4 | 0 | `—` |
| `MUT-META-ANNOT-ADD` | 22 | 0 | `—` |
| `MUT-META-ANNOT-REMOVE` | 5 | 0 | `—` |
| `MUT-META-LABEL-ADD` | 22 | 1 | `The ClusterRoleBinding "ingress-nginx-prod" is invalid: roleRef: Invalid valu...` |
| `MUT-META-LABEL-CHANGE` | 22 | 1 | `The ClusterRoleBinding "kube-state-metrics-dev" is invalid: roleRef: Invalid ...` |
| `MUT-META-PODANNOT-ADD` | 9 | 0 | `—` |
| `MUT-NP-ALLOW-ALL` | 7 | 0 | `—` |
| `MUT-NP-RULE-ADD` | 7 | 0 | `—` |
| `MUT-NP-RULE-REMOVE` | 6 | 0 | `—` |
| `MUT-POD-AUTOMOUNT` | 6 | 0 | `—` |
| `MUT-POD-HOST-NS` | 9 | 0 | `—` |
| `MUT-POD-HOSTPATH` | 12 | 0 | `—` |
| `MUT-POD-HOSTPORT` | 4 | 0 | `—` |
| `MUT-POD-SA-CHANGE` | 6 | 0 | `—` |
| `MUT-RBAC-ADD-RULE` | 9 | 0 | `—` |
| `MUT-RBAC-RES-WILDCARD` | 4 | 0 | `—` |
| `MUT-RBAC-ROLEREF-ADMIN` | 0 | 6 | `The RoleBinding "rabbitmq-prod-endpoint-reader" is invalid: roleRef: Invalid ...` |
| `MUT-RBAC-RULE-REMOVE` | 2 | 0 | `—` |
| `MUT-RBAC-SUBJECT-ADD` | 6 | 0 | `—` |
| `MUT-RBAC-VERB-WILDCARD` | 3 | 0 | `—` |
| `MUT-RES-LIMITS` | 7 | 0 | `—` |
| `MUT-RES-REMOVE` | 4 | 0 | `—` |
| `MUT-RES-REQUESTS` | 6 | 0 | `—` |
| `MUT-SC-ALLOW-ESC` | 4 | 0 | `—` |
| `MUT-SC-CAPS-ADD` | 12 | 0 | `—` |
| `MUT-SC-CAPS-DROP-ALL` | 3 | 0 | `—` |
| `MUT-SC-NONROOT` | 4 | 0 | `—` |
| `MUT-SC-PRIVILEGED` | 4 | 0 | `—` |
| `MUT-SC-READONLY-ROOT` | 5 | 0 | `—` |
| `MUT-SC-REMOVE` | 4 | 0 | `—` |
| `MUT-SC-RUN-AS-ROOT` | 6 | 0 | `—` |
| `MUT-SCALE-HPA` | 8 | 0 | `—` |
| `MUT-SCALE-PDB` | 14 | 0 | `—` |
| `MUT-SVC-PORT` | 6 | 0 | `—` |
| `MUT-SVC-SELECTOR` | 5 | 0 | `—` |
| `MUT-SVC-TYPE` | 6 | 0 | `—` |
| `MUT-WL-IMAGE` | 11 | 0 | `—` |
| `MUT-WL-PROBE-MODIFY` | 12 | 0 | `—` |
| `MUT-WL-PROBE-REMOVE` | 8 | 0 | `—` |
| `MUT-WL-PULLPOLICY` | 6 | 0 | `—` |
| `MUT-WL-REPLICAS` | 12 | 0 | `—` |
| `MUT-WL-SCHEDULING` | 9 | 0 | `—` |
| `MUT-WL-STRATEGY` | 7 | 2 | `The Deployment "ingress-nginx-dev-controller" is invalid: spec.strategy.rolli...` |
