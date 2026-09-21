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

### `data_sources`
`id`, `name` (único — ej. "TyC Sports", "Boca Juniors - sitio oficial"), `reliability_level` (texto libre, valores esperados "A"-"E" según la jerarquía concreta de ADR-0020 — sin enum cerrado a nivel BD para no requerir una migración si la jerarquía gana/pierde una fuente), `source_type` (ej. `official_club`/`official_federation`/`credentialed_journalist`/`established_outlet`/`aggregator`/`social_media`/`unverified`), `url` (nullable), `notes` (nullable), `active` (default `true`). Consumida por el Football Intelligence Agent (`.claude/agents/football-intelligence.md`).

### `player_availability`
Hecho estructurado de disponibilidad de un jugador (lesión, suspensión, duda, rotación), producido por el Football Intelligence Agent y persistido por un pipeline determinista de Data & Backend Platform — el agente cualitativo nunca escribe directo a esta tabla. `id`, `player_id`, `team_id` (obligatorio: `players` no tiene `team_id` propio, ver nota en esa tabla — acá hace falta explícitamente), `match_id` (nullable: un reporte de estado no siempre está atado a un partido concreto todavía), `status` (`unavailable`/`doubtful`/`available`/`rotation_risk`), `reason` (nullable: `muscle_injury`/`suspension`/`rotation`/`personal`/`unknown`), `confidence` (espeja el `reliability_level` de la fuente), `source_id` (FK a `data_sources`), `source_url` (nullable — el artículo/post específico, distinto de `data_sources.url`), `raw_fact` (jsonb, NOT NULL — el hecho estructurado completo tal como lo produjo el agente, para trazabilidad/auditoría total), más los 5 timestamps de abajo.

### `news_signals`
Señal contextual más amplia no atada a la disponibilidad de un jugador puntual (cambio de DT, noticia táctica, sanción administrativa). `id`, `team_id` (nullable), `match_id` (nullable), `signal_type` (`coaching_change`/`tactical_news`/`suspension_admin`/`other`), `description` (NOT NULL), `source_id`, `source_url` (nullable), `raw_fact` (jsonb, NOT NULL), más los mismos 5 timestamps que `player_availability`.

**Los 5 timestamps de `player_availability`/`news_signals`** (Regla P0 de anti-leakage, `.claude/agents/football-intelligence.md`) — nunca colapsados en uno solo:
- `event_time` (nullable): cuándo ocurrió el evento en el mundo real, si se conoce.
- `published_at` (nullable): cuándo la fuente lo publicó. Metadato informativo — nunca se usa como corte de disponibilidad.
- `observed_at` (NOT NULL): cuándo el proceso de investigación lo encontró.
- `ingested_at` (NOT NULL, default `now()`): cuándo quedó persistido en la base.
- `available_at` (NOT NULL): el corte real usado por el feature builder (`available_at <= as_of_timestamp` del snapshot correspondiente). Política por defecto: `available_at = observed_at`, nunca `published_at`.

Constraint a nivel BD en ambas tablas (`ck_player_availability_available_at_after_observed_at` / `ck_news_signals_available_at_after_observed_at`): `available_at >= observed_at`. Bloquea leakage retroactivo — un artículo publicado antes de que el sistema lo encontrara no puede "estar disponible" antes de haber sido observado.

### `bookmaker_snapshots`
Cuota 1X2 ("Match Winner") de un bookmaker para un partido, capturada vía el endpoint `/odds` de API-Football (ADR-0021) — solo benchmark externo, nunca feature del modelo de producción sin un ADR nuevo (regla no negociable de `CLAUDE.md` / ADR-0003 / ADR-0009). `id`, `match_id` (FK a `matches`), `bookmaker_name` (ej. "William Hill"), `odds_home`/`odds_draw`/`odds_away` (float, cuota decimal tal como la devuelve el proveedor), `captured_at` (timestamptz, NOT NULL — cuándo corrió nuestro script, un único valor compartido por corrida), `provider_updated_at` (timestamptz, nullable — el campo `update` de la respuesta del proveedor, cuándo API-Football dice que esa cuota cambió por última vez; metadato informativo, distinto de `captured_at`, no se usa como corte de disponibilidad), `raw_response` (jsonb, NOT NULL — el dict crudo por bookmaker tal como lo devuelve el proveedor, para trazabilidad). Único por `(match_id, bookmaker_name, captured_at)`.

A diferencia de `player_availability`/`news_signals`, esta tabla no tiene CheckConstraint anti-leakage: no hay un par `observed_at`/`available_at` que proteger — `captured_at` es simplemente cuándo se ejecutó la captura, no un corte de disponibilidad para el feature builder.

Poblada bajo demanda por `pipelines/capture_odds_snapshot.py` (partidos `status='scheduled'` con `kickoff_at` dentro de una ventana configurable, default 7 días) — solo mercado "Match Winner", sin cadencia automatizada todavía (deliberado, ver ADR-0021: automatizarla es trabajo de Fase 7).

## Diseñado, NO implementado todavía (deferido con trigger explícito en ADR-0013/0014/0019)

No existen en `models.py` ni tienen migración. Se listan acá para que el diseño no se pierda, no como estado actual:

- **`predictions`** / **`prediction_runs`** — el pipeline de predicción en vivo (Fase 7-8) todavía no existe.
- **`match_stats`** — estadísticas de partido más allá del resultado (goles, xG, etc.) — Fase 6+ si se justifica con backtesting.
- **`match_schedule_history`**, timestamps separados en `results` (`event_ended_at`/`provider_updated_at`/`observed_at`) — trigger explícito: Fase 7.
- **`score_90`/`score_extra_time`/`penalties_*`** en `results` — trigger explícito: primera competición con fase eliminatoria (ADR-0019).
- **`provider_entity_mappings`** genérico — rechazado en ADR-0013 mientras haya un solo proveedor real, no solo deferido.

## Compatibilidad con la visión evolutiva (ADR-0009)

`model_versions.status` (`candidate`/`production`/`retired`) ya es la semántica de Champion (`production`) vs. Challengers (`candidate`); un rollback es reasignar `status='production'` a un `model_versions.id` anterior, sin reentrenar. `parent_model_version_id` ya da linaje básico. Cuando exista el ensemble/meta-modelo, se espera agregar una tabla `ensemble_weights` — no se agrega ahora porque nada la usaría.

## Notas de diseño

- **Por qué `bookmaker_snapshots` no es input del modelo:** decisión explícita (ADR-0003, ADR-0021) — existe solo para comparación externa (benchmark), nunca como feature sin un ADR nuevo aprobado por el usuario.
- **Por qué `hyperparameters`/`features` son JSONB y no columnas explícitas:** el conjunto de features y la forma de los hiperparámetros evolucionan mientras se experimenta (ADR-0006); columnas rígidas obligarían a migraciones constantes durante la fase de experimentación.
- **Tablas explícitamente fuera de alcance:** usuarios/autenticación (no hay cuentas en el MVP), apuestas/bankroll (módulo futuro separado, ver ADR-0009).
