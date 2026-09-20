# ADR-0015 — Veredicto sobre revisión de `tests/` (5ta ronda de review externo)

**Estado:** Aceptada — la ronda con el hallazgo más grave hasta ahora
**Fecha:** 2026-09-20
**Decide:** CTO/Orquestador (Claude), a partir de una revisión externa (ChatGPT, vía el usuario)

## Contexto

Quinta revisión externa consecutiva, esta vez sobre `tests/`. A diferencia de rondas anteriores donde la mayoría de los hallazgos terminaban rechazados por prematuros, esta encontró **un problema real y grave**: CI no ejecutaba casi dos tercios de la suite.

## Hallazgo P0 confirmado — el más grave de las 5 rondas

**Verificado directamente contra el log real de GitHub Actions, no asumido:** `gh run view --log` mostró **16 passed, 28 skipped**. `conftest.py::db_session` hace `pytest.skip()` cuando no hay `DATABASE_URL`, y `ci.yml` nunca configuró una base de datos — así que **todos** los tests de constraints de esquema, anti-leakage temporal, evaluación y baselines se saltaban en silencio en cada corrida de CI de esta sesión. Cada "CI verde" reportado en las ADRs 0010-0014 certificaba solo la sexta parte de la suite real.

**Corregido:** `ci.yml` ahora levanta un contenedor de servicio `postgres:16` efímero (nunca Neon — se destruye al terminar el job), corre `alembic upgrade head` contra él, y expone `DATABASE_URL` al job de `pytest`. Verificado localmente que las 44+ pruebas (antes 16) corren.

## Otros hallazgos aceptados

- **`alembic check` agregado a CI** (verificado que el comando existe y funciona en nuestra versión pinneada, 1.13.3) — falla el build si `models.py` y las migraciones quedan desincronizados, en vez de depender de que alguien lo note manualmente (como pasó, dos veces, con reviews que asumían drift inexistente o ya corregido).
- **Bug real en mi propio test**: `test_tiny_negative_rounding_error_is_clamped` no pasaba ningún valor negativo (`0.5000000000001` no es negativo) — el nombre prometía probar el clamp de negativos y no lo ejercitaba. Corregido con un valor genuinamente negativo (`-1e-12`) por debajo de la tolerancia.
- **Tests adversariales de Dixon-Coles**: se agregó `TestDixonColesTauValidity`, usando exactamente la combinación matemática que la ronda 4 demostró (`λ=2, λ=2, ρ=0.3 → tau(0,0)=-0.2`), más un test de `predict_proba()` con esos parámetros forzados a mano (no dependiendo de que el optimizador "casualmente" llegue ahí) y un test de que `fit()` reporta `converged=False` honestamente con datos degenerados.
- **`results` ahora rechaza inconsistencia score/outcome** (ej. `home_score=3, away_score=0, outcome='draw'`) vía un nuevo `CheckConstraint`. La migración se aplicó sin error contra los 2243 resultados reales ya cargados — confirma que la ingesta siempre calculó `outcome` correctamente, pero cierra la puerta a que un bug futuro en otro código no lo haga.
- **El "happy path" de `test_schema_constraints.py` modelaba un estado inconsistente** (creaba un `Match` con `status='scheduled'` por defecto y le adjuntaba un `Result`) — corregido a `status="finished"` explícito.
- **Test de que el `StandardScaler` de la regresión logística no ve datos de eval**: nuevo `tests/test_logistic.py`, comparando el `mean_`/`scale_` del scaler devuelto por `fit()` contra un `StandardScaler` de referencia ajustado solo con los mismos datos de train.
- **Guarda estructural**: `test_build_features_never_includes_rotation_data` — si algún día alguien fusiona `build_features()` con `rotation_index` sin pensarlo, este test se rompe de inmediato en vez de introducir leakage silencioso.
- **Terminología**: los comentarios de `test_result_known_buffer_boundary` decían "partido que terminó" — corregido a "cuyo kickoff_at cae" (solo conocemos el kickoff, `RESULT_KNOWN_BUFFER` es una inferencia, no un timestamp real de fin de partido — mismo principio que ya se documentó en `.claude/rules/temporal-integrity.md` en la ronda 2, aplicado acá también a los comentarios de test).

## Rechazado por ahora (mismo criterio que ADR-0013/0014)

| Propuesta | Por qué se rechaza ahora | Trigger |
|---|---|---|
| `join_transaction_mode="create_savepoint"` en la sesión de test | Sugerencia técnica válida de SQLAlchemy para sesiones anidadas en transacciones de test, pero nuestro `conftest.py` ya revierte todo correctamente sin ella (verificado: la suite corrió 44+ tests sin dejar datos residuales) — no hay bug que corrija hoy | Si algún test empieza a dejar datos residuales pese al rollback |
| Test end-to-end del pipeline completo de evaluación (scaler, tuning, holdout, todo junto) | El test puntual de scaler-en-aislamiento (agregado en esta ronda) ya cubre el riesgo de leakage más probable; un test end-to-end de todo `pipelines/` es más caro y con más superficie de falsos positivos | Si aparece un bug real de leakage en el pipeline completo que un test aislado no habría capturado |
| Test de que `rotation_index` nunca se usa con `available_at > prediction_cutoff` | No existe todavía el campo `available_at` para lineups (`lineup_snapshots`, rechazado en ADR-0013) — no hay nada contra qué testear | Cuando se implemente `lineup_snapshots` con temporalidad real |
| Cadena de puertas CI completa (unit → data contracts → postgres → temporal → model validity → walk-forward → reproducibility → promotion gate → deployment smoke) | Visión correcta para cuando exista auto-retraining (ADR-0009); hoy con una suite de ~50 tests y sin pipeline automatizado, es organización prematura | Cuando exista automatización de entrenamiento/promoción |
| Testing del ciclo champion/challenger | El propio review lo marca P2 "incorporarlo cuando exista" — coincidimos | Cuando exista ese ciclo |

## Incidente durante esta misma ronda: la migración del nuevo CHECK constraint se generó vacía

Al implementar el `CheckConstraint` de consistencia score/outcome (arriba), `alembic revision --autogenerate` generó un archivo con `upgrade()`/`downgrade()` en blanco (`pass`) — **autogenerate de Alembic no detecta de forma confiable constraints CHECK nuevos**, limitación conocida y documentada del propio proyecto Alembic. Apliqué esa migración vacía sin leer su contenido primero (confiando en el mensaje "Generating ... done"), así que `alembic upgrade head` "tuvo éxito" sin crear el constraint en Neon. Lo detectó el test que acababa de escribir (`test_result_rejects_score_outcome_mismatch`, esperaba `IntegrityError` y no lo recibió) — exactamente el tipo de red de seguridad que esta ADR defiende.

Corregido escribiendo el DDL a mano (`op.create_check_constraint`) y reaplicando (`alembic stamp` al revision anterior + `alembic upgrade head` real, sin usar `downgrade()` porque habría fallado tratando de borrar un constraint que nunca se creó). Validado contra los 2243 resultados reales sin error.

**Importante:** el gate de `alembic check` agregado a CI en esta misma ronda **probablemente tampoco habría detectado este caso específico** — usa la misma lógica de comparación que autogenerate, con el mismo punto ciego para CHECK constraints. La lección real no es "confiar en la herramienta", es **leer siempre el contenido de una migración autogenerada antes de aplicarla**, en particular cuando el cambio incluye un `CheckConstraint`.

## Consecuencias

- Positivas: la suite ahora certifica lo que dice certificar. Este es el hallazgo de mayor impacto real de las 5 rondas de review — no por sofisticación, sino porque invalidaba silenciosamente la señal de "tests pasando" en la que me apoyé para reportar progreso varias veces esta sesión.
- Negativas: ninguna nueva — el costo (un service container en CI, gratis en GitHub Actions) es mínimo comparado con el problema que resuelve.
- Trigger de revisión: ninguno — esto queda como la configuración correcta permanente, no una decisión a reconsiderar.

## Fuentes

Verificación directa: `gh run view <run> --log` mostrando "16 passed, 28 skipped" antes del fix; `alembic check` ejecutado localmente contra Neon confirmando que el comando existe en Alembic 1.13.3; migración del nuevo `CheckConstraint` aplicada sin error contra los 2243 resultados reales ya en Neon.
