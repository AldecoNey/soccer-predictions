# ADR-0022 — Fase 6: ¿head-to-head aporta señal real, como candidato desplegable?

**Estado:** Aceptada
**Fecha:** 2026-09-24
**Decide:** Evaluation & Calibration (función)

## Contexto

`MASTER_ARCHITECTURE_V1.md` marca el historial head-to-head (H2H) entre los dos equipos de un partido como "candidato a testear y descartar en Fase 6, no como feature garantizada". Nunca se había construido ni evaluado. Se retomó este experimento el 2026-09-24, durante un hueco real del calendario (sin partidos de Liga Profesional Argentina entre el 22/9 y el 2/10 — probablemente fecha FIFA, verificado contra la tabla `matches`), en vez de esperar sin avanzar nada.

A diferencia de `rotation_index` (ADR-0011), H2H **no tiene el problema de oráculo**: solo usa partidos entre los mismos dos equipos ya finalizados antes de `as_of_timestamp` (mismo corte `RESULT_KNOWN_BUFFER` que el resto de `app/features.py`), información legítimamente disponible antes del kickoff del partido que se está evaluando. Por eso esta es una evaluación comparable a las de ADR-0010 (backtest real, no solo diagnóstico) — la conclusión, sea cual sea, aplica directamente a si vale la pena tener esta feature en producción.

## Metodología

`head_to_head_features(session, match_id, home_team_id, away_team_id, as_of_timestamp, window=5)` (`app/features_h2h.py`): últimos hasta 5 encuentros entre los dos equipos (en cualquier orden de localía histórico), calculando desde la perspectiva del equipo que es local en el partido evaluado: `home_win_rate`, `draw_rate`, `avg_goal_diff`. Sin encuentros previos (caso común, no un error): campos en `None`.

Regresión logística multinomial (mismo modelo que ADR-0011), vector extendido con 2 features (`h2h_home_win_rate`, `h2h_avg_goal_diff` — se excluyen `matches_played`/`draw_rate` del vector de entrada para mantener la comparación en el mismo espíritu que rotation_index, +2 features). Defaults neutros cuando no hay historial: `1/3` para `home_win_rate` (no informativo — no `0.0`, que implicaría falsamente "el local siempre pierde") y `0.0` para `avg_goal_diff`.

Walk-forward por temporada, mismos 4 folds que ADR-0011 (expandiendo 2022→2023→2024→2025→2026). Dos variantes, mismos datos base, única diferencia el feature H2H: `logistic_no_h2h` / `logistic_with_h2h`.

## Resultado

Corrida real contra Neon, 2026-09-24. Ambas variantes registradas en `model_versions` como `candidate` (`v1`), con artefacto serializado cargable (ADR-0018).

| Fold | Eval | `no_h2h` log_loss / brier / acc | `with_h2h` log_loss / brier / acc |
|---|---|---|---|
| 1 | 2023 (n=378) | 1.1502 / 0.6722 / 0.410 | 1.1553 / 0.6751 / 0.397 |
| 2 | 2024 (n=378) | 1.0796 / 0.6526 / 0.415 | 1.0795 / 0.6536 / 0.421 |
| 3 | 2025 (n=510) | 1.0779 / 0.6525 / 0.414 | 1.0803 / 0.6537 / 0.418 |
| 4 | 2026 (n=396) | 1.0812 / 0.6535 / 0.422 | 1.0811 / 0.6532 / 0.424 |
| **Agregado** | **n=1662** | **1.0955 / 0.6572 / 0.415** | **1.0974 / 0.6584 / 0.415** |

**H2H no muestra mejora.** En el agregado (la cifra que importa, no picking de fold), `no_h2h` gana en log loss (métrica principal, ADR-0007) y Brier; accuracy empata (0.415 ambas). Fold a fold el resultado es mixto (folds 2 y 4 favorecen levemente a `with_h2h` en algunas métricas, folds 1 y 3 al revés), pero las diferencias son chicas en términos absolutos en todos los folds, y no hay ninguna tendencia consistente que sugiera que con más datos H2H empezaría a aportar.

A diferencia de ADR-0011, esto **no** es un resultado diagnóstico con matices — es un backtest real de un candidato genuinamente desplegable, y el resultado es negativo igual. Consistente con la advertencia original del brief de no asumir que H2H aporta señal.

## Decisión

**Se descarta `head_to_head_features` como feature de producción**, con la misma metodología de "documentar y descartar" que ADR-0006/ADR-0011 establecen — no se elimina el código (`app/features_h2h.py`, `logistic.FEATURE_NAMES_WITH_H2H`, `pipelines/train_logistic_h2h.py` quedan en el repo como registro auditable del experimento), pero no se usa en el modelo en producción.

## Nota operacional (no relacionada al resultado del experimento)

Durante esta corrida, la conexión a Neon volvió a colgarse repetidamente (8-24 min sin excepción, mismo síntoma que motivó el fix de keepalives TCP en `app/db.py` durante ADR-0011) — la mitigación anterior no lo eliminó del todo. Se ajustaron los parámetros de keepalive más agresivos (detección esperada en ~25s en vez de ~60s) como mejora de mejor esfuerzo, no como solución confirmada. Se intentó además agregar `statement_timeout` vía `connect_args`, pero Neon rechaza ese parámetro en su endpoint *pooled* ("unsupported startup parameter", verificado en vivo — rompía todos los tests) y se revirtió. Este experimento en particular se completó gracias a un cache en disco scopeado solo a `pipelines/train_logistic_h2h.py` (no toca infraestructura compartida). Se documenta como riesgo operacional conocido, no bloqueante hoy — revisar en serio si se vuelve crítico al construir el pipeline en vivo de Fase 7.

## Consecuencias

- Positivas: pregunta cerrada con evidencia real, no queda como duda abierta en el roadmap. La metodología (walk-forward respetando `RESULT_KNOWN_BUFFER`) queda como plantilla reutilizable para el próximo candidato de feature que se quiera testear.
- Negativas: ninguna sobre el producto — el código del experimento queda como documentación viva, no como deuda técnica activa.
- Trigger de revisión: si en el futuro se agrega una competición nueva (Copa Argentina, Libertadores) donde el historial H2H entre rivales de copa tenga una dinámica distinta a la liga regular, reevaluar con un ADR nuevo — no asumir que el resultado de acá se traslada automáticamente a ese contexto.

## Fuentes

Resultado generado por `backend/pipelines/train_logistic_h2h.py` corrido contra Neon el 2026-09-24. Verificación de que no hay partidos de Liga Profesional Argentina entre 2026-09-22 y 2026-10-02: consulta directa a la tabla `matches`, mismo día.
