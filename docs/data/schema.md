# Modelo de datos

Esquema relacional (PostgreSQL, Neon). Diseñado para soportar snapshots inmutables (ADR-0008), control anti-leakage (ADR-0007) y expansión futura a más competiciones sin reescritura.

**Este documento distingue explícitamente lo implementado (existe en `backend/app/models.py`, con migración aplicada en Neon) de lo diseñado pero no construido todavía** — la confusión entre ambas cosas fue una fuente real de reviews basados en fotos desactualizadas del repo (ver ADR-0018). `backend/app/models.py` es la fuente de verdad final; esto es un resumen legible, no al revés.

Convenciones: todas las tablas tienen `id` (UUID), `created_at`. Las tablas con datos que cambian en el tiempo guardan también un timestamp explícito de corte (`as_of_timestamp`, `generated_at`, etc.) — nunca se infiere el tiempo desde `created_at`.

## Implementado (Fases 2-6)

### `competitions`
`id`, `name`, `country`, `api_football_id` (int, único — ej. `128` para Liga Profesional Argentina, ver ADR-0003), `external_ids` (jsonb, mapeo genérico a otros proveedores si se agregan), `active`.

### `seasons`
`id`, `competition_id`, `year_label`, `start_date`, `end_date`. Único por `(competition_id, year_label)`.

### `teams`
`id`, `name`, `short_name`, `country`, `api_football_id` (único), `external_ids` (jsonb).

### `players`
`id`, `name`, `api_football_id` (único). **No tiene `team_id`** — deliberado, no un descuido: el equipo de un jugador se infiere de en qué `match_lineups` aparece, para no tener que mantener "equipo actual" mutable ni reconstruir plantillas históricas a partir de un campo que solo refleja el presente.

### `matches`
`id`, `season_id`, `home_team_id`, `away_team_id`, `kickoff_at` (timestamptz — se actualiza en cada re-ingesta si el proveedor reprograma el partido, ver ADR-0014), `venue`, `matchday` (string libre — Liga Profesional usa fases como "2nd Phase - 1", no solo fechas numéricas), `status` (`scheduled`/`postponed`/`finished`/`cancelled`), `api_football_id` (único), `external_ids`. Constraints: local ≠ visitante, índice en `kickoff_at`.

### `results`
`id`, `match_id` (único — un resultado por partido), `home_score`, `away_score` (≥0), `outcome` (`home`/`draw`/`away`), `finalized_at`. Constraint: `outcome` debe ser consistente con el marcador (ej. `home_score=3, away_score=0, outcome='draw'` está bloqueado a nivel BD, ver ADR-0015). **`outcome`/scores representan el resultado a 90' + descuento** (ADR-0019) — nunca prórroga/penales; irrelevante hoy (liga sin fase eliminatoria) pero ver el ADR antes de ingerir la primera copa.

### `match_lineups`
Titulares de un partido. `id`, `match_id`, `team_id`, `player_id`, `position`. Único por `(match_id, team_id, player_id)`. Usado por `rotation_index` (`app/features_lineup.py`) — señal de investigación/oracle, NO segura para T-72/T-24 (ver `.claude/rules/temporal-integrity.md`).

### `feature_snapshots`
`id`, `match_id`, `horizon` (`T-72`/`T-24`/`T-2`), `generated_at`, `features` (jsonb), `dataset_version`. **Existe pero ningún pipeline le escribe todavía** — todas las features se calculan al vuelo (`app/features.py::build_features`). Se empieza a poblar cuando el pipeline en vivo (Fase 7) lo necesite para auditoría real.

### `model_versions`
`id`, `name`, `version_tag`, `algorithm_family` (`naive`/`elo`/`poisson_dixon_coles`/`logistic`/`gbm`/`ensemble`), `training_dataset_version`, `hyperparameters` (jsonb — para `logistic` incluye el modelo serializado, pickle+base64, ver ADR-0018), `trained_at`, `promoted_at`, `status` (`candidate`/`production`/`retired`), `git_sha`, `git_dirty` (ADR-0014), `parent_model_version_id` (linaje, nullable). Único por `(name, version_tag)`.

### `evaluation_metrics`
`id`, `model_version_id`, `evaluation_run_at`, `segment` (texto libre: `overall`, `fold=2023`, etc. — sin columna `horizon` separada todavía, ver razonamiento en `app/models.py::EvaluationMetric`), `log_loss`, `brier_score`, `ece` (nullable), `accuracy`, `n_samples`.

## Diseñado, NO implementado todavía (deferido con trigger explícito en ADR-0013/0014/0019)

No existen en `models.py` ni tienen migración. Se listan acá para que el diseño no se pierda, no como estado actual:

- **`predictions`** / **`prediction_runs`** — el pipeline de predicción en vivo (Fase 7-8) todavía no existe.
- **`bookmaker_snapshots`** — benchmark de mercado (ADR-0003), pendiente de confirmar cobertura de The Odds API o usar API-Football odds (ver discusión en ADR-0018 sobre capturador prospectivo).
- **`player_availability`**, **`news_signals`**, **`data_sources`** — Football Intelligence Agent no está activado todavía (ver `.claude/agents/football-intelligence.md`); cuando se active, `news_signals`/`player_availability` usan 5 timestamps (`event_time`/`published_at`/`observed_at`/`ingested_at`/`available_at`), no uno solo.
- **`match_stats`** — estadísticas de partido más allá del resultado (goles, xG, etc.) — Fase 6+ si se justifica con backtesting.
- **`match_schedule_history`**, timestamps separados en `results` (`event_ended_at`/`provider_updated_at`/`observed_at`) — trigger explícito: Fase 7.
- **`score_90`/`score_extra_time`/`penalties_*`** en `results` — trigger explícito: primera competición con fase eliminatoria (ADR-0019).
- **`provider_entity_mappings`** genérico — rechazado en ADR-0013 mientras haya un solo proveedor real, no solo deferido.

## Compatibilidad con la visión evolutiva (ADR-0009)

`model_versions.status` (`candidate`/`production`/`retired`) ya es la semántica de Champion (`production`) vs. Challengers (`candidate`); un rollback es reasignar `status='production'` a un `model_versions.id` anterior, sin reentrenar. `parent_model_version_id` ya da linaje básico. Cuando exista el ensemble/meta-modelo, se espera agregar una tabla `ensemble_weights` — no se agrega ahora porque nada la usaría.

## Notas de diseño

- **Por qué no hay tabla de odds como input del modelo:** decisión explícita (ADR-0003) — cualquier snapshot de cuotas existe solo para comparación externa, nunca como feature sin un ADR nuevo aprobado por el usuario.
- **Por qué `hyperparameters`/`features` son JSONB y no columnas explícitas:** el conjunto de features y la forma de los hiperparámetros evolucionan mientras se experimenta (ADR-0006); columnas rígidas obligarían a migraciones constantes durante la fase de experimentación.
- **Tablas explícitamente fuera de alcance:** usuarios/autenticación (no hay cuentas en el MVP), apuestas/bankroll (módulo futuro separado, ver ADR-0009).
