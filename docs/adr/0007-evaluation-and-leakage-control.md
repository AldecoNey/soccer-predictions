# ADR-0007 — Metodología de evaluación, calibración y control de data leakage

**Estado:** Aceptada
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude), ejecutado por Evaluation & Calibration Agent

## Contexto

Sección 7 y 14-15 del brief marcan esto como crítico: el sistema no puede medirse por accuracy simple, y ninguna predicción puede usar información que en la realidad no habría estado disponible en el momento del snapshot (T-72h, T-24h, T-2h).

## Decisión

### Validación temporal (obligatoria, nunca random split)

- **Walk-forward / expanding window**: se entrena con todo lo anterior a una fecha de corte, se evalúa sobre el período inmediatamente posterior, se avanza el corte, se repite. Nunca se usa un split aleatorio de partidos porque rompe el orden temporal y permite que información "futura" relativa a un partido contamine su entrenamiento.
- Cada snapshot (T-72/T-24/T-2) se evalúa con SU PROPIO conjunto de features disponibles a ese horizonte — un modelo evaluado en T-72 no puede usar features que solo existen en T-24 o T-2 (p.ej. alineación confirmada).

### Métricas (en este orden de prioridad)

1. **Log Loss** (métrica principal de optimización — penaliza fuertemente la sobreconfianza mal calibrada).
2. **Brier Score** (verificación cruzada de calibración/discriminación).
3. **Calibration curves + Expected Calibration Error (ECE)** — reportado por rango de probabilidad, no solo agregado.
4. **Accuracy** — métrica secundaria/informativa únicamente, nunca criterio de promoción de un modelo.
5. Desglose obligatorio por: horizonte (T-72/T-24/T-2), local/visitante, rango de confianza, y (cuando haya más de una) por competición.

### Comparación obligatoria contra 4 referencias

1. Baseline ingenuo (ADR-0006).
2. Baseline de fuerza histórica (Elo/Poisson).
3. Modelo candidato.
4. Consenso de bookmaker, SOLO cuando exista una cuota temporalmente comparable al mismo horizonte (nunca comparar una predicción T-72 contra una cuota tomada T-2 sin advertirlo explícitamente).

### Promoción/rechazo de modelos

Un modelo nuevo reemplaza al desplegado únicamente si:
- mejora log loss y calibración de forma consistente en el walk-forward validation (no un solo período favorable);
- lo evalúa el Evaluation & Calibration Agent, nunca el mismo agente que lo entrenó;
- la mejora y la metodología quedan documentadas en un ADR de modelo (`docs/adr/NNNN-model-vX.md`) antes de desplegar.

### Controles anti-leakage (checklist obligatorio antes de cualquier entrenamiento o backtest)

- [ ] Ninguna feature usa datos con timestamp posterior al `generated_at` del snapshot que se está prediciendo.
- [ ] Ningún resultado (`results`) se usa como input de un snapshot anterior al kickoff del propio partido.
- [ ] Datos corregidos retroactivamente (p.ej. una estadística oficial revisada días después) NO se usan para reconstruir snapshots pasados — el snapshot almacenado es inmutable (ver ADR-0008).
- [ ] La ventana de forma reciente (últimos 3/5/8/10 partidos) se calcula solo con partidos anteriores al timestamp del snapshot.
- [ ] Cross-validation temporal, nunca k-fold aleatorio, en cualquier proceso de selección de hiperparámetros.
- [ ] El conjunto de test final (holdout) no se toca durante la selección de modelo — solo se usa una vez, al final, para el reporte de evaluación final.

### Calibración

Se investigan Platt scaling, isotonic regression y temperature scaling (adaptado a 3 clases), y se aplican SOLO si demuestran mejora fuera de muestra frente al modelo sin calibrar adicional — no por defecto.

## Consecuencias

- Positivas: previene el error más común y más dañino en sistemas predictivos deportivos (leakage silencioso que infla métricas de forma artificial).
- Negativas: el pipeline de evaluación es más lento de construir que un simple train/test split, pero es un costo no negociable dado el objetivo declarado del producto (credibilidad estadística).
- Trigger de revisión: ninguno previsto — esta es una política estructural, no una decisión de stack que cambie con el tiempo.

## Fuentes

Metodología basada en prácticas estándar de validación temporal en forecasting y en la literatura de calibración probabilística (Platt 1999, Zadrozny & Elkan 2002 para isotonic regression); no requiere verificación de pricing/fuentes externas.
