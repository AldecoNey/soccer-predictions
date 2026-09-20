# ADR-0014 — Veredicto sobre revisión de `app/` (4ta ronda de review externo)

**Estado:** Aceptada — mezcla real de bugs corregidos y sobre-ingeniería rechazada
**Fecha:** 2026-09-20
**Decide:** CTO/Orquestador (Claude), a partir de una revisión externa (ChatGPT, vía el usuario)

## Contexto

Cuarta revisión externa consecutiva, esta vez sobre el código real de `app/` (no solo docs/schema). A diferencia de las rondas 1-3, esta trajo **bugs matemáticos y de diseño genuinos**, no solo preferencias arquitectónicas — se verificó cada claim contra el código antes de decidir, como en las rondas anteriores.

## Verificación previa

1. **"Alembic y ORM desincronizados" (P0 según el review) — FALSO al momento de leerlo.** `alembic current` y `alembic heads` coinciden (`95ee57001aca`). El review se generó sobre una foto del repo anterior al commit de la ronda 3 (`6037f1f`), que ya había agregado `git_sha`/`parent_model_version_id` con su migración correspondiente. No hacía falta ninguna corrección — ya estaba resuelto.
2. **`MatchLineup.created_at` duplicado — CONFIRMADO.** Bug real y trivial (Python simplemente usa la segunda definición), corregido.

## Decisión — Aceptado (bugs reales, corregidos en esta sesión)

- **`rest_days` medía la cosa equivocada.** Antes: `as_of_timestamp - último_partido`, lo que hacía que el mismo partido tuviera "descanso" distinto según el horizonte del snapshot (T-72 vs T-2) sin que hubiera ocurrido ningún partido nuevo — no tiene sentido futbolístico. Corregido a `match.kickoff_at - último_partido` (el kickoff del partido que se predice, un dato ya conocido de antemano, no leakage). Nuevo test de regresión (`test_rest_days_is_gap_to_target_kickoff_not_to_snapshot`) verifica explícitamente que el mismo partido da el mismo `rest_days` en T-72 y en T-2.
- **Dixon-Coles podía generar `tau(x,y) < 0`**, y por lo tanto celdas de "probabilidad" negativas en la grilla de inferencia — matemáticamente demostrado por el review (`λ=2, λ=2, ρ=0.3` → `tau(0,0)=-0.2`), y posible con nuestros bounds actuales (`ρ ∈ [-0.3, 0.3]`). Corregido: `predict_proba()` clampea celdas negativas a 0 antes de normalizar (mitigación estándar en implementaciones de Dixon-Coles, no oculta el problema) y valida el resultado final contra un contrato común (`app/prediction_models/contract.py::validate_probability_triple`) antes de devolverlo.
- **Un ajuste de Dixon-Coles no convergido igual se registraba como candidato válido.** Corregido: `train_baselines.py` ahora aborta (no registra el modelo) si `converged=False`, en vez de solo imprimirlo informativamente.
- **Contrato común de validación**, pedido explícitamente por el review ("no confiar en que cada modelo lo haga bien por su cuenta"): `naive.predict_proba`, `elo.predict_proba`, `poisson_dixon_coles.predict_proba` y `logistic.predict_proba` ahora pasan todos por `validate_probability_triple` (finito, no-negativo, suma≈1) antes de devolver nada.
- **`git_sha` solo no bastaba** — un working tree con cambios sin commitear invalida la trazabilidad. Agregado `git_dirty` (columna + `app/git_info.py::is_git_dirty()`, vía `git status --porcelain`), conectado en los 3 scripts de entrenamiento junto a `git_sha`. No se implementó todavía un gate duro que bloquee promoción con tree sucio — se registra el estado, la decisión de bloquear queda para cuando exista un mecanismo de promoción real (no solo yo leyendo el output y decidiendo a mano).
- **`get_historical_matches` no scopeaba por competición** — mismo patrón de bug que ya se había encontrado y corregido en `get_folds` (ADR-0007). Se agregó `competition_id: uuid.UUID | None = None` (default preserva el comportamiento actual exacto, ya que solo hay una competición cargada) — el mecanismo queda listo para cuando se agregue una segunda competición, sin forzar cambios en los call-sites hoy.

## Decisión — Ya resuelto en rondas anteriores, sin cambios nuevos

- El enmarcado de `rotation_index` como "oracle/diagnostic, no comparable a producción" ya se corrigió en la ronda 2 (commit `136bc02`) — el review pide exactamente eso, ya está.
- La naturaleza aproximada del buffer de 3h (`RESULT_KNOWN_BUFFER`) como "fallback de reconstrucción histórica, no verdad de dominio" también ya se documentó en la ronda 2 (`.claude/rules/temporal-integrity.md`).

## Decisión — Rechazado por ahora (mismo criterio que ADR-0013: no construir para necesidades hipotéticas)

| Propuesta | Por qué se rechaza ahora | Trigger de reconsideración |
|---|---|---|
| Cliente API-Football como "conector de producción" (raw response, paging, rate-limit tracking, `ingestion_run_id`) | Un solo proveedor, ingesta histórica ya completada, sin problema de paginación real hoy (los 3 endpoints que usamos no lo necesitan) | Cuando la ingesta pase a ser continua/en vivo (Fase 7) y la confiabilidad ante 429/5xx importe operacionalmente, no solo arquitectónicamente |
| `TrainingRun` como tabla separada de `ModelVersion` | No hay pipeline de entrenamiento automatizado — "correr un script a mano" no necesita su propia tabla de runs todavía | Cuando exista automatización de entrenamiento (ADR-0009, todavía no autorizada) |
| Interfaz común `fit(training_context)`/`predict_proba(prediction_context)` entre modelos | Prematuro mientras el ensemble/dispatcher que la necesitaría (ADR-0009) no existe — forzar una interfaz común ahora con 4 modelos y ningún consumidor genérico es abstracción sin usuario real | Cuando se construya el meta-modelo/ensemble o el dispatcher de Fase 7 |
| `models.py` dividido en módulos (`app/db/models/*.py`) | 240 líneas, 9 clases — todavía legible como archivo único; dividir ahora agrega fricción de imports sin necesidad real mientras el esquema sigue cambiando en casi cada commit | Cuando supere ~500-600 líneas o el cambio de esquema se estabilice |
| `config.py` con validación fail-fast por capability, `SecretStr` | Un solo operador (yo) configurando `.env` manualmente — no hay proceso mal configurado corriendo desatendido todavía | Fase 7 (automatización en vivo, donde un proceso mal configurado sí podría ejecutarse sin supervisión) |
| `/health` → `/live` + `/ready` | No hay dependencias externas críticas que el health check deba verificar todavía (no hay backend desplegado sirviendo tráfico real) | Cuando el backend (Fase 8) esté desplegado y sirviendo |
| ECE por clase (home/draw/away) en vez de solo top-label | Refinamiento válido de `app/evaluation.py`, pero el top-label ECE actual ya cumple su función para las decisiones tomadas hasta ahora (ADR-0010/0011) | Cuando la calibración por clase sea relevante para una decisión real de promoción |
| `DEFAULT_REST_DAYS=7` + indicador `rest_days_missing` en vez de imputación simple | Válido para modelos tabulares más sofisticados (GBM); con regresión logística como candidato 3, la imputación uniforme no invalida la comparación con/sin rotación ya hecha (ambas variantes usan la misma imputación) | Al llegar a GBM (ADR-0006) o si se detecta que la imputación distorsiona resultados |
| Gate duro "working tree sucio → no promocionable" | Se registra `git_dirty`, pero no hay mecanismo de promoción automatizado que bloquear — hoy la promoción es una decisión humana (mía) que ya puede consultar ese campo | Cuando exista un mecanismo de promoción real, no manual |

## Consecuencias

- Positivas: se corrigieron 2 bugs matemáticos/lógicos reales (`rest_days`, Dixon-Coles) que habrían distorsionado silenciosamente resultados futuros si no se detectaban ahora; se estableció un contrato de validación compartido en vez de confiar en cada modelo por separado.
- Negativas: el experimento de `rotation_index` que corre en paralelo a esta ADR se hizo con la definición ANTERIOR (rota) de `rest_days` — no se invalida retroactivamente (la comparación con/sin rotación seguía siendo justa, ambas variantes usaban la misma versión rota de forma consistente), pero se nota explícitamente: si se quiere repetir ese experimento con la definición corregida, hay que volver a correrlo.
- Trigger de revisión: cada fila de la tabla de rechazos tiene su propio disparador explícito, igual que ADR-0013.

## Fuentes

Verificación directa: `alembic current`/`alembic heads` (contradice la premisa P0 del review), lectura de `app/models.py` (confirma el duplicado en `MatchLineup`), y verificación matemática manual de `tau(0,0) = 1 - λ_x·λ_y·ρ` con los bounds actuales de `ρ`.
