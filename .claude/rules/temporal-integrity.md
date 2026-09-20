---
paths:
  - "backend/app/features*.py"
  - "backend/app/prediction_models/**/*.py"
  - "backend/app/evaluation*.py"
  - "backend/pipelines/**/*.py"
  - "backend/tests/test_features*.py"
  - "backend/tests/test_evaluation.py"
  - "backend/tests/test_baselines.py"
  - "backend/app/dataset*/**/*.py"
  - "backend/app/calibration*/**/*.py"
---

# Integridad temporal / anti-leakage

Esta regla se carga automáticamente al tocar código de features, modelos, evaluación o pipelines — el mismo principio está descrito en `CLAUDE.md` (regla 1) y en ADR-0007, pero acá está el detalle operativo para no tener que repetirlo en cada archivo. Cubre también directorios que todavía no existen (dataset building, calibration) para no tener que acordarse de ampliar esto cuando aparezcan.

## Regla no negociable

Ningún dato usado en un cálculo puede tener timestamp de disponibilidad posterior al `as_of_timestamp` efectivo del snapshot/predicción que lo usa. T-72/T-24/T-2 son etiquetas de horizonte, no timestamps — el corte real siempre es un `as_of_timestamp` explícito.

## Principio transversal: toda tabla con información cambiante necesita semántica temporal explícita

No es solo para `news_signals`/señales cualitativas. Cualquier tabla cuyo contenido pueda variar según cuándo se consulte (resultados, alineaciones, lesiones, cuotas, lo que sea que se agregue después) debe poder responder "¿esto estaba disponible en el momento X?" de forma explícita — nunca inferirlo de cuándo se procesó o de una regla ad hoc distinta por fuente. El feature builder debe poder hacer siempre la misma pregunta (`available_at <= as_of_timestamp`), no una regla diferente por tabla.

## Mecanismos ya implementados (no reinventar)

- `app/features.py::RESULT_KNOWN_BUFFER` (3h): **fallback de reconstrucción histórica**, no una verdad de dominio. No afirma "a las 3h el resultado se conoce" — afirma "no tenemos timestamp real de disponibilidad para datos históricos viejos, así que usamos un margen conservador range hacia atrás desde kickoff_at". En operación prospectiva (Fase 7+), cuando exista un timestamp real de cuándo el propio sistema observó que el partido terminó (`result_available_at`/`observed_at`), ese dato real manda sobre el buffer fijo.
  - Sobre `Result.finalized_at`: no usarlo como proxy de cuándo ocurrió el partido en el mundo real (representa cuándo NOSOTROS lo cargamos, casi siempre mucho después). Pero sí es válido usarlo como cota conservadora de disponibilidad si se necesita un "definitivamente ya estaba disponible en este momento" — la carga siempre ocurre después del evento real, nunca antes, así que como cota superior no introduce leakage (solo puede ser pesimista, nunca optimista).
- `app/prediction_models/data.py::get_historical_matches(session, as_of_timestamp)`: única función autorizada para traer histórico de partidos respetando el buffer — no reimplementar la query en otro lado.
- `app/features_lineup.py::rotation_index`: **experimento oracle/diagnóstico, no un backtest comparable a los de producción**. Usa la alineación REAL del propio partido — usarla en cualquier validación etiquetada como T-72/T-24 sigue siendo leakage, sin excepción, incluso si se llama "backtesting". Solo sirve para responder "¿esta clase de señal tiene algo de poder predictivo en general?", nunca para reportar una métrica como si fuera la de un modelo desplegable. Una versión real y desplegable a T-2 (o al horizonte que corresponda) requeriría un `observed_at` real de cuándo el sistema efectivamente vio la alineación confirmada — no hay una constante de minutos-antes-del-kickoff asumida en ningún lado del código: eso variaría por liga/proveedor y se mide, no se supone.
- Para señales cualitativas (Football Intelligence Agent, todavía no activado): la regla equivalente es `available_at <= as_of_timestamp`, con `available_at` nunca anterior a `observed_at` — ver `.claude/agents/football-intelligence.md`.

## Checklist antes de mergear código nuevo que toque esto

- [ ] ¿Toda consulta a datos históricos pasa por una función que ya aplica el corte temporal, o se reimplementó el filtro a mano? (si es lo segundo, revisar dos veces)
- [ ] ¿Hay un test que verifique el borde exacto del corte (no solo "casos obviamente pasados/futuros")? Ver `test_features.py::test_result_known_buffer_boundary` como ejemplo del patrón esperado.
- [ ] ¿La validación de cualquier modelo nuevo usa walk-forward temporal, nunca random split?
- [ ] ¿El holdout final de test se usó una sola vez, no para seleccionar hiperparámetros? (ver `pipelines/tune_elo.py` para el patrón train/validation/test correcto). Una vez inspeccionado un holdout y reportado su resultado, sus datos no pueden alimentar otra ronda de selección y seguir llamándose "holdout final" — eso es simplemente un holdout nuevo que hay que nombrar como tal, y el anterior queda consumido.
