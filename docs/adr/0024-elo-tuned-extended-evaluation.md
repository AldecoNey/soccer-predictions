# ADR-0024 — Validación extendida de `elo_tuned` con folds 2025/2026: INCONCLUSIVE, no se promueve

**Estado:** Aceptada
**Fecha:** 2026-09-24
**Decide:** Evaluation & Calibration (función), ejecutado por Orquestador

## Contexto

ADR-0010 encontró que `elo_tuned` (k=10, home_advantage=120, seleccionados con train=2022/validation=2023, nunca re-tuneados) le ganaba a `naive` en el único fold de test disponible entonces (2024: log_loss 1.0570 vs 1.0611) — pero un solo fold no alcanza el estándar de ADR-0007 ("mejora consistente... a través de múltiples ventanas temporales"), así que quedó como `candidate`, no promovido.

Con el plan Pro de API-Football ya activo (ADR-0003), las temporadas 2025 y 2026 están disponibles — dos folds adicionales genuinamente independientes, sin re-tunear ningún hiperparámetro (2023 sigue "gastado" como validación, no se reutiliza como si fuera evidencia nueva).

## Metodología

`k_factor=10`/`home_advantage=120` **fijos** (no re-tuneados). Walk-forward expandiendo (mismos folds que ADR-0011/0022): eval=2025 (train 2022-2024) y eval=2026 (train 2022-2025) como evidencia nueva; 2023/2024 solo como chequeo de reproducibilidad de ADR-0010, no contados como evidencia independiente adicional.

## Resultado (con datos corregidos post-ADR-0019, ver esa ADR para el detalle de la corrección)

| Fold | Tipo | `elo_tuned` log_loss | `naive` log_loss | Gap relativo | ¿elo gana? |
|---|---|---|---|---|---|
| 2023 | gastado (validación original) | 1.0610 | 1.0675 | 0.61% | sí |
| 2024 | gastado (test original, ADR-0010) | 1.0570 | 1.0611 | 0.39% | sí |
| **2025** | **nueva evidencia** (n=510) | **1.0866** | **1.0879** | **0.12%** | sí, apenas |
| **2026** | **nueva evidencia** (n=405) | **1.0708** | **1.0792** | **0.78%** | sí |

`elo_tuned` gana en los 4 folds — la dirección es consistente, 2024 no fue un golpe de suerte aislado. Pero un análisis de significancia (bootstrap pareado, 10.000 remuestreos, sobre la diferencia de log-loss por partido) mostró que **el margen en 2025 es estadísticamente indistinguible de cero** (IC 95% cruza cero ampliamente, elo gana en solo ~57% de los remuestreos — básicamamente una moneda), mientras que 2026 muestra una señal más convincente (~90% de los remuestreos favorecen a elo) pero tampoco alcanza significancia al 95% convencional. El fold con más muestra (2025) es justo el que tiene el margen más débil — el patrón opuesto al que se esperaría de un efecto real y estable.

**Calibración (ECE) empeora para `elo_tuned` respecto a `naive`** en ambos folds nuevos (2025: 0.0491 vs 0.0305; 2026: 0.0356 vs 0.0003) — con la salvedad de que `naive` emite una única probabilidad constante por temporada, lo que mecánicamente le da menos oportunidad de estar mal calibrado. Aun así, la dirección consistente (elo peor calibrado en los dos folds nuevos) es una señal real que ADR-0007 pide pesar, no solo log loss.

**Hallazgo adicional, con ADR propia (ADR-0019, actualización 2026-09-24):** las temporadas 2025/2026 no son un round-robin simple como 2022-2024 — incluyen fase eliminatoria real (Apertura/Clausura + playoffs, formato nuevo de la liga desde 2025). Esto mezcla partidos de liga regular con partidos de eliminación directa (sin implicancia de descenso, dinámica de incentivos distinta) bajo una sola etiqueta de "temporada" en los folds de walk-forward — algo que nunca aplicó a los folds limpios 2022-2024 que originalmente validaron el diseño de este esquema. No se corrigió el diseño de folds en esta ADR (afecta también a ADR-0011/ADR-0022 retroactivamente) — queda como pendiente explícito.

## Decisión

**INCONCLUSIVE — no se promueve `baseline_elo` a `production`.** No es un REJECT (no hay evidencia de que `elo_tuned` sea peor que naive; gana en los 4 folds probados) ni un PROMOTE (el margen no es estadísticamente distinguible de ruido en el fold más grande de evidencia nueva, la calibración empeora, y los folds nuevos mezclan estructuras de torneo heterogéneas que nunca se auditaron para este propósito).

Se registra `model_versions` `baseline_elo` `version_tag="v2-extended-eval"` (status=`candidate`, padre = v2 original) con las métricas de esta evaluación en `evaluation_metrics`, sin tocar la fila v2 original.

## Próximos pasos (pendientes, no decididos acá)

1. **A Data & Backend Platform:** auditar si `Season` debería partirse a nivel de torneo (Apertura/Clausura, fase regular/eliminatoria) en vez de un año calendario — afecta el diseño de folds de todo Fase 6 en adelante, no solo esta evaluación.
2. **A Modeling & Feature Engineering:** el gap de calibración es candidato concreto para un calibrador post-hoc (Platt/isotónica/temperature scaling) ajustado solo con datos de entrenamiento — no intentado acá, fuera de alcance de esta evaluación.
3. **Práctico:** esperar al menos un fold adicional limpio (o una estructura de folds a nivel de torneo) antes de reabrir la pregunta de promoción — hoy hay efectivamente 2 puntos de evidencia nueva y no concuerdan en magnitud/significancia.

## Consecuencias

- Positivas: se resuelve el pendiente explícito de ADR-0010 con evidencia real, no se fuerza una promoción sin base. El proceso encontró además un bug de integridad de datos real (ver ADR-0019) que de otro modo hubiera quedado sin detectar.
- Negativas: sigue sin haber un modelo en producción — información real, no una falla del pipeline.
- Trigger de revisión: nuevo fold limpio disponible, o resolución del punto 1 de "próximos pasos" (folds a nivel de torneo).

## Fuentes

`backend/pipelines/evaluate_elo_tuned_extended.py`, corrido contra Neon el 2026-09-24 (antes y después de la corrección de ADR-0019 — los números de esta tabla son post-corrección). Análisis de significancia (bootstrap pareado) realizado ad-hoc durante la evaluación, no persistido como script reutilizable.
