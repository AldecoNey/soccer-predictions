# ADR-0011 — Fase 6: ¿rotation_index aporta señal real?

**Estado:** Borrador — pendiente de completar con el resultado final de `pipelines/train_logistic.py` (corriendo al momento de crear este archivo; no se completa con números hasta tener el resultado real, ver CLAUDE.md "nunca inventes resultados").
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

**Nota metodológica importante:** `rotation_index` usa la alineación REAL del propio partido evaluado — es decir, esta prueba mide el valor de **saber la alineación confirmada**, no es una feature segura para T-72/T-24 tal cual. Corresponde más a un horizonte T-2 o, más precisamente, al momento real en que se confirman las alineaciones (~20 minutos antes del kickoff según observación del usuario, 2026-09-20) — no a las 2 horas que se usó como proxy en `NEAR_KICKOFF_OFFSET` para el resto de las features de forma reciente en este mismo experimento.

## Resultado

_Pendiente — completar con la salida real de `pipelines/train_logistic.py` una vez termine. No completar con números aproximados o "esperados"._

## Decisión sobre el 4to snapshot (T-confirmación de alineaciones)

El brief original (Sección 6) autoriza explícitamente proponer una 4ta actualización de pronóstico basada en alineaciones confirmadas, pero **solo si los datos demuestran que mejora las predicciones** — nunca por defecto. Esta ADR es la evidencia que esa decisión requiere. Se decide en conjunto con el usuario una vez completado el resultado de arriba, no antes.

## Fuentes

Resultado generado por `backend/pipelines/train_logistic.py` corrido contra Neon el 2026-09-20.
