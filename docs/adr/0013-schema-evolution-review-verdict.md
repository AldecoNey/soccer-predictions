# ADR-0013 — Veredicto sobre propuesta de evolución de esquema (Alembic/schema)

**Estado:** Aceptada — mayormente como rechazo justificado, con 2 cambios chicos aceptados
**Fecha:** 2026-09-20
**Decide:** CTO/Orquestador (Claude), a partir de una revisión externa (ChatGPT, vía el usuario)

## Contexto

Una revisión externa de la cadena de migraciones Alembic (confirmó que la cadena en sí es correcta y lineal, sin ramas rotas) propuso una evolución de esquema sustancial: tabla de historial de reprogramaciones (`match_schedule_history`), timestamps múltiples en `results`, ampliación grande de `feature_snapshots` y `model_versions` (incluyendo `artifact_sha256`, `dependency_lock_hash`, estados `challenger`/`shadow`/`rejected`), separación de `evaluation_runs` y `evaluation_metrics`, `provider_entity_mappings` genérico en vez de `api_football_id`, `player_team_membership`, `lineup_snapshots` con estado probable/confirmado, y modelado estructurado de `matchday`/resultados de copa.

## Verificación previa a decidir

Antes de aceptar o rechazar nada, se verificaron dos hechos concretos contra el código real (no se asumió nada de la premisa del review):

1. **`feature_snapshots` no está poblada por ningún pipeline todavía** — la tabla existe desde Fase 3, pero ningún script (`train_baselines.py`, `evaluate_baselines.py`, `tune_elo.py`, `train_logistic.py`) le escribe una fila. Toda predicción/feature se calcula al vuelo.
2. **`Player` nunca tuvo un campo de equipo actual** — no hay `team_id` en el modelo. La crítica de que "inferir el equipo actual de las alineaciones complica reconstruir historial" ataca un problema que no existe en nuestro esquema.

## Decisión

**Aceptado (implementado en esta misma sesión):**
- `model_versions.git_sha` y `model_versions.parent_model_version_id`: columnas nuevas, nullable, sin romper nada existente. Dan trazabilidad real ("con qué código exacto se entrenó esto", "de qué versión viene") a costo casi cero — no requieren un pipeline de entrenamiento automatizado para tener valor, se completan solas en cada corrida (`app/git_info.py::get_git_sha()`, ya conectado en `train_baselines.py`, `tune_elo.py`, `train_logistic.py`).
- Documentación de que el downgrade de la migración `94407e13dc47` (matchday String→Integer) no es realmente reversible una vez que existen valores no numéricos — un comentario, sin cambio de comportamiento.

**Rechazado por ahora, con trigger de revisión explícito (no es un "no" permanente):**

| Propuesta | Por qué se rechaza ahora | Cuándo reconsiderar |
|---|---|---|
| `match_schedule_history`, timestamps múltiples en `results` | No existe todavía tabla `predictions` ni automatización en vivo — no hay nada que una reconstrucción retroactiva necesite explicar todavía | Al implementar Fase 7 |
| Ampliar `feature_snapshots` (`as_of_timestamp`, `feature_schema_version`, `git_sha`, etc.) | La tabla no se usa — ampliar un esquema no poblado es trabajo especulativo | Cuando algún pipeline empiece a escribir ahí de verdad |
| Resto de campos grandes en `model_versions` (`artifact_sha256`, `dependency_lock_hash`, `training_run_id`, estados challenger/shadow/rejected) | No hay artifacts serializados (los "modelos" son JSONB de parámetros ajustados) ni pipeline de entrenamiento automatizado que genere "training runs" distintos de correr un script a mano | Cuando exista automatización de entrenamiento (visión de ADR-0009, todavía no autorizada a construirse) |
| `evaluation_runs` separado de `evaluation_metrics` | Un solo protocolo de evaluación (walk-forward por temporada), usado un puñado de veces manualmente — no hay "múltiples protocolos" que distinguir todavía | Cuando exista un segundo protocolo de evaluación real |
| `provider_entity_mappings` genérico en vez de `api_football_id` | **Rechazo de fondo, no solo de timing.** Un solo proveedor real (API-Football). `external_ids` (JSONB) ya permite crecer a más proveedores sin la columna dedicada si hiciera falta. Construir la tabla genérica ahora es la sobre-ingeniería que el proyecto evita explícitamente (Sección 28 del brief, CLAUDE.md) | Cuando se incorpore un segundo proveedor de datos real |
| `player_team_membership` | Premisa incorrecta — no existe el campo que supuestamente había que corregir | N/A, no aplica |
| `lineup_snapshots` con estado probable/confirmado | Para partidos ya jugados solo existe una alineación final; la distinción probable/confirmado solo importa en operación en vivo | Fase 7 (alineaciones en tiempo real) |
| `matchday` estructurado (stage/round/group), distinción `score_90`/penales | El propio review coincide en que no es urgente ("no lo construiría todavía") — sin desacuerdo, sin acción | Al incorporar copas (Sección 25 del brief — Copa Argentina, Libertadores) |

## Consecuencias

- Positivas: se evita construir infraestructura para problemas que no existen todavía (multi-proveedor, entrenamiento automatizado, múltiples protocolos de evaluación), consistente con ADR-0009 ("esta visión no autoriza construir nada de eso antes de que el roadmap llegue a esa etapa"). Se capturan las 2 mejoras genuinamente baratas.
- Negativas: si alguna de estas necesidades aparece antes de lo esperado (ej. se agrega Copa Argentina antes de lo planeado), habrá que volver a esta ADR y construir lo que corresponda entonces — aceptado como el costo normal de no construir prematuramente.
- Trigger de revisión: cada fila de la tabla de arriba tiene su propio trigger explícito.

## Fuentes

Verificación directa contra `backend/app/models.py` y `backend/pipelines/*.py` (grep confirmando que `FeatureSnapshot` no se inserta en ningún pipeline, y que `Player` no tiene `team_id`) — no se aceptó la premisa del review sin comprobarla.
