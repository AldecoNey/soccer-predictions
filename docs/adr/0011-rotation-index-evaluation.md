# ADR-0011 — Fase 6: ¿rotation_index aporta señal real?

**Estado:** Aceptada
**Fecha:** 2026-09-20
**Decide:** Evaluation & Calibration (función)

## Contexto

Fase 6 (ROADMAP) exige que toda feature nueva demuestre mejora medible en backtesting antes de quedar en el modelo — si no aporta, se documenta y se descarta (mismo criterio que ADR-0006 aplica a H2H). Se construyó `rotation_index` (fracción del once titular que cambió respecto al partido anterior del mismo equipo, ver `app/features_lineup.py`) a partir de las alineaciones reales de los 2243 partidos finalizados (Fase 2 extendida a 2022-2026, ver ADR-0003).

Se introdujo además el candidato 3 de ADR-0006 (regresión logística multinomial, `app/prediction_models/logistic.py`) como vehículo para esta prueba, ya que Elo/Poisson-Dixon-Coles no aceptan features contextuales directamente.

## Metodología

Walk-forward por temporada (4 folds, expandiendo con las 5 temporadas disponibles tras el upgrade a Pro):

- Fold 1: train=2022 → eval=2023
- Fold 2: train=2022-2023 → eval=2024
- Fold 3: train=2022-2024 → eval=2025
- Fold 4: train=2022-2025 → eval=2026

Dos variantes por fold, mismos datos, misma configuración de modelo, única diferencia el feature de rotación:
- `logistic_no_rotation`: forma reciente (PJ/PPG/diferencia de gol/descanso, ventana 5) de ambos equipos.
- `logistic_with_rotation`: lo mismo + `rotation_index` de ambos equipos.

Features estandarizadas (`StandardScaler`, ajustado solo con datos de train) antes de entrenar — sin esto, la regularización L2 de la regresión logística penaliza desigual features de escalas muy distintas, lo que habría distorsionado la comparación (encontrado y corregido en el camino, no un ajuste posterior para forzar un resultado).

**Nota metodológica importante (corregida tras segunda revisión, 2026-09-20):** este experimento NO es un backtest comparable a los de ADR-0010 — es un **experimento oracle/diagnóstico**. `rotation_index` usa la alineación REAL del propio partido evaluado, algo que no existe en T-72/T-24 y que en T-2 tampoco existe "tal cual" sin trabajo adicional. Mide únicamente si esta clase de señal tiene poder predictivo en principio, nunca reporta un número comparable al de un modelo desplegable. No se asume ninguna constante de "minutos antes del kickoff" para cuándo se confirman las alineaciones — eso varía por liga/proveedor y, si se construye una versión real para Fase 7, se mide con un `observed_at` real, no se supone. (Versión anterior de esta nota asumía "~20 minutos" citando una observación del usuario como si fuera un dato medido — era una entrada válida para abrir la pregunta, no una fuente para codificar como constante.)

## Caveat metodológico adicional (3ra revisión, ADR-0018)

`logistic.vectorize()` usa `_safe(rotation.get("home"), default=0.0)` — si `rotation_index()` devuelve `None` (alineación insuficiente del partido actual o del anterior), ese `None` se convierte en `0.0`, el mismo valor que "rotación real cero" (once idéntico al partido anterior). Son dos cosas distintas ("no sé" vs. "no hubo cambios") que este experimento no distingue. No se repitió el experimento con una muestra estrictamente filtrada (ambos equipos con lineup completa del partido actual y el anterior) porque los folds ya completados al momento de este caveat no mostraban una mejora que estuviera en duda por este motivo — si el resultado final hubiera sido ambiguo, este habría sido el primer paso antes de sacar una conclusión.

## Resultado

Corrida completa el 2026-09-20/21 contra Neon (post-fix de keepalives TCP en `app/db.py` — la primera corrida se había colgado 22+ min sin error por una conexión muerta sin FIN/RST, no relacionado con el experimento en sí). Ambas variantes registradas en `model_versions` como `candidate` (`v1`).

| Fold | Eval | `no_rotation` log_loss / brier / acc | `with_rotation` log_loss / brier / acc |
|---|---|---|---|
| 1 | 2023 (n=378) | 1.1502 / 0.6722 / 0.410 | 1.1562 / 0.6748 / 0.402 |
| 2 | 2024 (n=378) | 1.0796 / 0.6526 / 0.415 | 1.0810 / 0.6543 / 0.413 |
| 3 | 2025 (n=510) | 1.0779 / 0.6525 / 0.414 | 1.0794 / 0.6537 / 0.410 |
| 4 | 2026 (n=396) | 1.0812 / 0.6535 / 0.422 | 1.0779 / 0.6513 / 0.424 |
| **Agregado** | **n=1662** | **1.0955 / 0.6572 / 0.415** | **1.0968 / 0.6581 / 0.412** |

**`rotation_index` no muestra señal predictiva.** En 3 de los 4 folds (1, 2, 3), la variante con rotación es peor en las tres métricas simultáneamente; en el fold 4 es marginalmente mejor. En el agregado de las 1662 evaluaciones, `no_rotation` gana en log loss (métrica principal, ADR-0007), Brier y accuracy. Las diferencias son pequeñas en términos absolutos, pero consistentemente a favor de no incluir la señal — no hay ningún indicio de mejora que valga la pena perseguir con una muestra mayor.

Esto es un resultado más fuerte de lo que parece a primera vista: el experimento usa la alineación REAL de cada partido (ventaja de oráculo, imposible de tener en producción a T-72/T-24 y no garantizada tal cual a T-2). Si ni siquiera con esa ventaja injusta `rotation_index` mejora las predicciones, es muy improbable que una versión realista (con `observed_at` real y confirmación tardía) sí lo haga.

## Decisión sobre el 4to snapshot (T-confirmación de alineaciones)

El brief original (Sección 6) autoriza explícitamente proponer una 4ta actualización de pronóstico basada en alineaciones confirmadas, pero **solo si los datos demuestran que mejora las predicciones** — nunca por defecto. El resultado de arriba no lo demuestra — al contrario, hasta con ventaja de oráculo la señal no ayuda. **Se descarta agregar un 4to snapshot T-confirmación de alineaciones en esta etapa del proyecto.** No se cierra la puerta de forma permanente: si en el futuro cambia la fuente de datos (alineaciones confirmadas mucho antes del kickoff, por ejemplo) o se agregan otras señales de rotación (ej. minutos jugados acumulados, no solo XI titular), se puede reabrir con un ADR nuevo — pero no hay base para construirlo ahora.

Por el criterio de ADR-0018 (rigor documentado, no "encontrar mejora"), este candidato específico (`rotation_index`) queda cerrado: la evaluación fue walk-forward, sin leakage relevante (es un experimento oracle declarado como tal desde el diseño), y el resultado —negativo— queda documentado con evidencia completa. **Esto no cierra Fase 6 en su totalidad**: el alcance de Fase 6 en `ROADMAP.md` también incluye `player_availability`/`news_signals` poblados y `player_availability_score` como feature, que dependen de activar el Football Intelligence Agent — todavía no hecho. Eso sigue pendiente.

## Fuentes

Resultado generado por `backend/pipelines/train_logistic.py` corrido contra Neon el 2026-09-20.
