# Modelo de datos V1

Esquema relacional (PostgreSQL) para el MVP de Primera División Argentina. Diseñado para soportar snapshots inmutables (ADR-0008), control anti-leakage (ADR-0007) y expansión futura a más competiciones sin reescritura (ver `docs/roadmap/ROADMAP.md`).

Convenciones: todas las tablas tienen `id` (UUID), `created_at` (timestamp, inmutable). Las tablas de eventos temporales guardan también `as_of` o `generated_at` explícito — nunca se infiere el tiempo desde `created_at` de la fila.

## Entidades núcleo

### `competitions`
Liga o torneo (ej. "Liga Profesional de Fútbol Argentina"). Permite agregar competiciones por configuración (Sección 4 del brief).
Campos clave: `id`, `name`, `country`, `external_ids` (jsonb — mapeo a IDs de cada proveedor externo, ej. `{"api_football": 44}`), `active`.

### `seasons`
Temporada de una competición (ej. 2026). `id`, `competition_id`, `year_label`, `start_date`, `end_date`.

### `teams`
`id`, `name`, `short_name`, `external_ids` (jsonb), `country`.

### `players`
`id`, `name`, `team_id` (actual, mutable — la plantilla histórica se reconstruye vía `player_availability`, no vía este campo), `external_ids`.

### `matches`
`id`, `season_id`, `home_team_id`, `away_team_id`, `kickoff_at` (timestamp con timezone — crítico para calcular los horizontes T-72/T-24/T-2 correctamente), `venue`, `matchday`, `status` (scheduled/postponed/finished/cancelled), `external_ids`.

## Datos contextuales

### `match_stats`
Estadísticas post-partido (goles, tiros, posesión, xG si está disponible). `id`, `match_id`, `team_id`, `stat_name`, `stat_value`, `source_id`, `recorded_at`. Diseño clave-valor (en vez de una columna por stat) para poder incorporar nuevas métricas sin migraciones.

### `player_availability`
Disponibilidad de un jugador para un partido específico, en un momento específico (crítico para T-72/T-24/T-2 — la disponibilidad cambia entre snapshots). `id`, `match_id`, `player_id`, `status` (available/doubtful/injured/suspended/rotation_risk), `as_of` (timestamp de cuándo se supo este dato), `source_id`, `confidence_level`.

### `news_signals`
Señales cualitativas estructuradas por el Football Intelligence Agent. `id`, `match_id` (nullable — algunas señales son sobre el club en general), `team_id`, `signal_type` (ej. `manager_change`, `rotation_expected`, `travel_fatigue`), `structured_value` (jsonb), `raw_text_excerpt`, `source_id`, `published_at`, `processed_at`, `confidence_level`.

### `data_sources`
Jerarquía de fuentes (Sección 10 del brief). `id`, `name`, `tier` (A/B/C/D/E), `url`, `reliability_notes`.

## Predicción y modelado

### `model_versions`
`id`, `name`, `version_tag` (semver o hash de git commit), `algorithm_family` (elo/poisson_dixon_coles/logistic/gbm/ensemble), `training_dataset_version`, `hyperparameters` (jsonb), `trained_at`, `promoted_at` (nullable — null hasta que pasa evaluación), `status` (candidate/production/retired).

### `feature_snapshots`
Valores de features usados para UNA predicción específica, congelados en el tiempo (clave para reproducibilidad y anti-leakage). `id`, `match_id`, `horizon` (T-72/T-24/T-2), `generated_at`, `features` (jsonb — vector completo de features con sus valores), `dataset_version`.

### `prediction_runs`
Una ejecución del pipeline de predicción (puede generar predicciones para varios partidos). `id`, `triggered_by` (scheduled/manual), `horizon`, `started_at`, `finished_at`, `status`, `model_version_id`.

### `predictions`
**Append-only** (ADR-0008). `id`, `match_id`, `prediction_run_id`, `model_version_id`, `feature_snapshot_id`, `horizon`, `generated_at`, `prob_home`, `prob_draw`, `prob_away` (suman 1, constraint a nivel BD), `prob_home_public`, `prob_away_public` (normalizadas sin empate, ver Sección 5 del brief), `invalidated_at` (nullable), `invalidation_reason` (nullable).

### `bookmaker_snapshots`
Cuotas externas, solo benchmark (Sección 8 del brief — nunca feature del modelo). `id`, `match_id`, `bookmaker`, `captured_at`, `odds_home`, `odds_draw`, `odds_away`, `implied_prob_home`, `implied_prob_draw`, `implied_prob_away` (ya des-vigorizadas), `margin_removed_method`.

## Resultados y evaluación

### `results`
`id`, `match_id`, `home_score`, `away_score`, `outcome` (home/draw/away), `finalized_at`. Nunca se usa para recalcular una `prediction` ya emitida — solo se compara en la capa de evaluación.

### `evaluation_metrics`
Resultado de una corrida de evaluación (versionada, nunca sobreescrita). `id`, `model_version_id`, `evaluation_run_at`, `horizon`, `segment` (ej. `home`, `away`, `competition=44`, `confidence_band=0.6-0.7`), `log_loss`, `brier_score`, `ece`, `accuracy`, `n_samples`, `compared_against` (baseline_naive/baseline_strength/bookmaker/previous_production_model).

## Compatibilidad con la visión evolutiva (ADR-0009)

Verificado explícitamente: el esquema actual no necesita romperse para soportar Champion/Challenger y ensembles a futuro. `model_versions.status` (`candidate`/`production`/`retired`) ya es la semántica de Champion (`production`) vs. Challengers (`candidate`); un rollback es simplemente reasignar `status='production'` a un `model_versions.id` anterior, sin reentrenar. Cuando se implemente el ensemble/meta-modelo (fuera del alcance de V1), se espera agregar campos como `parent_version_id` (linaje de challengers) y una tabla `ensemble_weights` — no se agregan ahora porque nada los usaría todavía.

## Notas de diseño

- **Por qué no hay tabla `odds` como input del modelo:** decisión explícita (ADR-0003, Sección 8 del brief) — `bookmaker_snapshots` existe solo para comparación externa, ningún proceso de features debe leerla como input de entrenamiento sin un ADR nuevo que apruebe ese cambio de metodología.
- **Por qué `features` y `structured_value` son JSONB y no columnas explícitas:** el conjunto de features evolucionará mientras se experimenta (ADR-0006); usar columnas rígidas obligaría a migraciones constantes durante la fase de experimentación. Se puede "endurecer" a columnas explícitas más adelante si un subconjunto de features se estabiliza y se requiere mejor performance de consulta.
- **Tablas explícitamente NO incluidas en V1** (por simplicidad, ver Sección 28 del brief — no acumular tablas sin justificación): tablas de usuarios/autenticación (no hay cuentas en el MVP), tablas de apuestas/bankroll (módulo futuro separado, Sección 24 del brief).
