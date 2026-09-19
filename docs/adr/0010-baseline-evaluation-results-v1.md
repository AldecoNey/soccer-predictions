# ADR-0010 — Resultado de la evaluación de baselines V1: ninguno supera a naive

**Estado:** Aceptada (registro de hallazgo empírico, no una decisión de arquitectura)
**Fecha:** 2026-09-19
**Decide:** Evaluation & Calibration (función), reportado al usuario para decidir próximo paso

## Contexto

Walk-forward validation (ADR-0007) de los 3 baselines de ADR-0006 sobre Liga Profesional Argentina 2022-2024, con 2 folds de ventana expansiva:

- Fold 1: entrenar con 2022 (581 partidos) → evaluar 2023 (378 partidos).
- Fold 2: entrenar con 2022+2023 (959 partidos) → evaluar 2024 (378 partidos).

## Resultado

| Modelo | Log Loss (agregado, n=756) | Brier | Accuracy | ECE |
|---|---|---|---|---|
| **baseline_naive** | **1.0643** | **0.6437** | **0.448** | 0.0187 |
| baseline_elo | 1.0717 | 0.6493 | 0.418 | 0.0189 |
| baseline_poisson_dixon_coles | 1.0837 | 0.6577 | 0.410 | 0.0685 |

**Naive gana en log loss (la métrica principal, ADR-0007) en ambos folds por separado, no solo en el agregado.** Las diferencias son pequeñas en términos absolutos (~2% entre naive y poisson_dixon_coles) pero consistentes en dirección. Accuracy también favorece a naive — notablemente, Elo y Poisson-DC aciertan MENOS que simplemente predecir siempre "gana el local" (que es lo que naive hace implícitamente, dado que p_home=43.8% es la clase más probable).

## Análisis de causas plausibles (no se investigaron todas exhaustivamente — quedan como hipótesis a probar, no como hechos verificados)

1. **Hiperparámetros de Elo sin calibrar.** `k_factor=20` y `home_advantage=60` son valores de sentido común tomados de la literatura general de Elo, nunca ajustados a este dataset específico. Es la explicación más probable y la más barata de descartar.
2. **Equipos ascendidos sin historial.** 2 de 28 equipos en 2023 y 2 de 28 en 2024 no tienen partidos previos en el set de entrenamiento del fold correspondiente — Elo los trata con `initial_rating` neutro y Poisson-DC devuelve fallback uniforme (1/3, 1/3, 1/3) para esos partidos. Es un número pequeño de partidos afectados, pero con cero información en vez de una estimación razonable (ej. rating promedio de la categoría inferior), así que empeora desproporcionadamente esos casos puntuales.
3. **Señal de fuerza relativa débil dentro de una sola temporada.** Con 378 partidos/temporada y 28 equipos, cada equipo juega ~27 partidos — una muestra chica para que Elo/Poisson-DC estimen fuerza relativa con precisión, especialmente al principio de cada temporada cuando Elo arranca todos los equipos en 1500.
4. **La conversión Elo→1X2 (tasa de empate constante, ADR-0006) puede estar perdiendo información** que si varía con la diferencia de rating.

No se determinó cuál de estas causas domina — requeriría experimentos adicionales (ver Sección "Próximos pasos").

## Decisión

**Ningún modelo se promueve a `production`.** Ni siquiera naive — no es candidato a producción, es la vara de comparación. Los 3 quedan como `candidate` en `model_versions`. Esto es exactamente el comportamiento correcto según ADR-0007: "no desplegar automáticamente una versión nueva simplemente porque es más compleja" — aquí ninguna versión, compleja o no, demuestra mejora, así que no se despliega ninguna.

El criterio de finalización de la Fase 5 tal como está escrito en `docs/roadmap/ROADMAP.md` ("al menos un modelo supera al Baseline 0 de forma estadísticamente consistente") **NO se cumple todavía con los baselines actuales sin ajustar**. Esto no es una falla del pipeline de evaluación (que funciona correctamente y está testeado) — es información real sobre el estado actual de los modelos.

## Próximos pasos posibles (para decidir con el usuario, no elegido unilateralmente aquí)

1. **Ajustar hiperparámetros de Elo** (k_factor, home_advantage) mediante una búsqueda acotada, evaluada con el mismo esquema walk-forward pero cuidando de no usar el fold de test final para seleccionar el hiperparámetro (requeriría un split adicional de validación dentro del fold de entrenamiento, o aceptar el riesgo documentado de tunear sobre los mismos folds de reporte — a discutir explícitamente si se elige esta opción, por la regla de ADR-0007 de no seleccionar el mejor modelo con el mismo dataset de test final).
2. **Avanzar a Fase 6** (features contextuales: lesiones, rotación, descanso) antes de seguir puliendo baselines — la hipótesis siendo que más información, no más ajuste de los mismos 3 modelos simples, es lo que realmente va a mover la aguja.
3. **Probar el candidato de regresión logística** de ADR-0006 (el siguiente escalón de complejidad autorizado) antes de seguir en Elo/Poisson-DC.

## Consecuencias

- Positivas: el pipeline de evaluación es honesto y no infla resultados — exactamente el objetivo declarado del producto (Sección 2 del brief: "no quiero porcentajes inventados").
- Negativas: la Fase 5 se cierra con la infraestructura completa y testeada, pero sin un "ganador" — se necesita una decisión explícita del usuario/CTO sobre cuál de los 3 próximos pasos tomar antes de continuar.

## Actualización (2026-09-19): Elo ajustado sí supera a naive, en un fold

Siguiendo la opción 1 de "Próximos pasos", se corrió `backend/pipelines/tune_elo.py`: búsqueda de `k_factor`/`home_advantage` con separación estricta train=2022 / validation=2023 / test=2024 (el fold de test nunca participó en la selección de hiperparámetros, respetando ADR-0007).

- Mejor combinación en validación: **k=10, home_advantage=120** (log_loss=1.0610 en 2023).
- Se verificó explícitamente que no era un artefacto de borde de la grilla inicial: se extendió la búsqueda a k∈{1,3,5,8,10} × home_advantage∈{120,150,180,220} y el mínimo se confirma en k=10/home_advantage=120 — valores más bajos de k y más altos de home_advantage empeoran el ajuste, no lo siguen mejorando.
- **Evaluado en el fold de test real (2024, nunca tocado durante la selección): elo_tuned log_loss=1.0570 vs. naive log_loss=1.0611 en el mismo fold — elo_tuned gana.** Mejora modesta (~0.4% relativo) pero en la dirección esperada, y confirma que el ajuste de rating sí aporta señal (k=10 le gana claramente a k≈1, que sería casi no actualizar ratings — descarta la hipótesis de que la mejora sea solo "naive disfrazado").

**Por qué NO se promueve todavía a `production`:** esta comparación usa un único fold de test (2024) — 2023 quedó consumida como validación para elegir hiperparámetros, así que ya no sirve como evidencia independiente. ADR-0007 exige mejora consistente "a través de múltiples ventanas temporales", y un solo fold no alcanza ese estándar por más que el resultado sea alentador. Se registra como `model_versions` `baseline_elo` `v2`, status=`candidate`.

**Próximo paso natural:** cuando haya más temporadas disponibles (temporada 2025 si se resuelve el acceso vía plan pago — ver ADR-0003 — o al incorporar Copa Argentina/otras competiciones), repetir esta validación con un fold de test adicional antes de considerar la promoción. Por ahora, se recomienda avanzar a Fase 6 (features contextuales) en paralelo, ya que más señal es más prometedor que seguir extrayendo jugo de un ajuste de 2 hiperparámetros sobre 3 temporadas.

## Fuentes

Resultado generado por `backend/pipelines/evaluate_baselines.py` y `backend/pipelines/tune_elo.py` corridos contra Neon el 2026-09-19, persistido en `evaluation_metrics` y `model_versions`.
