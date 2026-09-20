---
paths:
  - "backend/app/features*.py"
  - "backend/app/prediction_models/**/*.py"
  - "backend/pipelines/**/*.py"
  - "backend/tests/test_features*.py"
  - "backend/tests/test_evaluation.py"
  - "backend/tests/test_baselines.py"
---

# Integridad temporal / anti-leakage

Esta regla se carga automáticamente al tocar código de features, modelos o pipelines — el mismo principio está descrito en `CLAUDE.md` (regla 1) y en ADR-0007, pero acá está el detalle operativo para no tener que repetirlo en cada archivo.

## Regla no negociable

Ningún dato usado en un cálculo puede tener timestamp de disponibilidad posterior al `as_of_timestamp` efectivo del snapshot/predicción que lo usa. T-72/T-24/T-2 son etiquetas de horizonte, no timestamps — el corte real siempre es un `as_of_timestamp` explícito.

## Mecanismos ya implementados (no reinventar)

- `app/features.py::RESULT_KNOWN_BUFFER` (3h): un partido recién cuenta como "conocido" 3h después de su kickoff — el resultado real no existe instantáneamente al pitazo inicial. Nunca usar `Result.finalized_at` como corte (registra cuándo LO CARGAMOS nosotros, no cuándo ocurrió).
- `app/prediction_models/data.py::get_historical_matches(session, as_of_timestamp)`: única función autorizada para traer histórico de partidos respetando el buffer — no reimplementar la query en otro lado.
- `app/features_lineup.py::rotation_index`: caso especial documentado — usa la alineación REAL del propio partido, por lo tanto NO es leakage-safe para T-72/T-24. Solo válido como señal de investigación/backtesting hasta que Fase 7 defina su integración real al horizonte T-2 (o al momento real de confirmación de alineaciones, ~20min pre-kickoff).
- Para señales cualitativas (Football Intelligence Agent, todavía no activado): la regla equivalente es `available_at <= as_of_timestamp`, con `available_at` nunca anterior a `observed_at` — ver `.claude/agents/football-intelligence.md`.

## Checklist antes de mergear código nuevo que toque esto

- [ ] ¿Toda consulta a datos históricos pasa por una función que ya aplica el corte temporal, o se reimplementó el filtro a mano? (si es lo segundo, revisar dos veces)
- [ ] ¿Hay un test que verifique el borde exacto del corte (no solo "casos obviamente pasados/futuros")? Ver `test_features.py::test_result_known_buffer_boundary` como ejemplo del patrón esperado.
- [ ] ¿La validación de cualquier modelo nuevo usa walk-forward temporal, nunca random split?
- [ ] ¿El holdout final de test se usó una sola vez, no para seleccionar hiperparámetros? (ver `pipelines/tune_elo.py` para el patrón train/validation/test correcto)
