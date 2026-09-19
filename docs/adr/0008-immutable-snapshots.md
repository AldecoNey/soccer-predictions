# ADR-0008 — Snapshots de predicción inmutables (append-only)

**Estado:** Aceptada
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude)

## Contexto

Sección 21 y 28 del brief: cada predicción debe poder auditarse retroactivamente, y está explícitamente prohibido "modificar retrospectivamente predicciones almacenadas" o "borrar errores históricos para mejorar métricas".

## Decisión

- Las tablas `predictions` y `prediction_runs` son **append-only**: nunca se hace `UPDATE` sobre una fila ya escrita, solo `INSERT`. Si una predicción fue generada con un bug, se corrige el bug y se genera un nuevo registro con nueva `generated_at`; el registro erróneo se conserva y se marca (`invalidated_at`, `invalidation_reason`), nunca se borra ni se sobreescribe.
- Cada fila de `predictions` referencia de forma inmutable: `model_version_id`, `feature_snapshot_id`, y las fuentes de datos usadas (vía `data_sources` / timestamps), de modo que el resultado sea 100% reproducible después del hecho.
- Los resultados reales (`results`) se agregan cuando están disponibles, pero **nunca sobreescriben ni recalculan** una predicción ya generada — la comparación predicción-vs-resultado se hace en la capa de evaluación, no modificando la predicción original.
- Las métricas de evaluación (`evaluation_metrics`) se recalculan y versionan por corrida de evaluación (con su propio timestamp), nunca se sobreescribe un cálculo anterior in place — así es posible ver cómo cambió el entendimiento del rendimiento del modelo a lo largo del tiempo.

## Consecuencias

- Positivas: garantiza auditabilidad total y elimina la tentación (accidental o no) de "limpiar" el historial para mejorar métricas reportadas.
- Negativas: el volumen de filas crece más rápido que en un esquema mutable; mitigado porque el volumen esperado (una liga, ~pocos cientos de partidos/temporada × 3 snapshots) es pequeño para el free tier de BD elegido (ADR-0002).
- Trigger de revisión: si el volumen de datos históricos crece mucho (multi-liga, multi-temporada) y el costo de almacenamiento se vuelve relevante, evaluar una política de archivado (mover snapshots antiguos a almacenamiento frío) sin violar el principio de inmutabilidad.

## Fuentes

N/A — principio de diseño derivado directamente de los requisitos explícitos del brief (Secciones 21 y 28).
