# ADR-0009 — Arquitectura evolutiva: ensembles, Champion/Challenger y aprendizaje continuo

**Estado:** Aceptada como visión de largo plazo (NO implementada todavía — ver "Estado de implementación" al final)
**Fecha:** 2026-09-19
**Decide:** Usuario (visión de producto/negocio) + CTO/Orquestador (Claude, arquitectura técnica)

## Contexto

Los baselines de la Fase 4 (naive, Elo, Poisson/Dixon-Coles — ADR-0006) **no son el motor predictivo final del proyecto**. Son el punto de partida de un proceso de investigación empírica continua. El objetivo de largo plazo es un sistema que:

- combine progresivamente múltiples familias de modelos (estadísticos, ML, bayesianos, temporales, xG-based, y eventualmente redes neuronales si el volumen/calidad de datos lo justifica);
- incorpore features contextuales (plantillas, lesiones, alineaciones, rotación, fatiga, viajes, árbitros, clima, calendario) a medida que se validen (Fase 6 y más allá);
- se combine mediante un meta-modelo/ensemble que aprenda dinámicamente qué modelos confiar según liga, equipos y contexto;
- se retroalimente automáticamente con resultados reales, bajo un esquema Champion/Challenger controlado — nunca aprendizaje ciego sobre resultados recientes.

Esta ADR fija los principios y restricciones que esa arquitectura debe cumplir, para que el trabajo de las Fases 4-10 no tenga que reconstruirse cuando el proyecto avance hacia esto. **No autoriza construir nada de esto ahora** — el roadmap (`docs/roadmap/ROADMAP.md`) sigue mandando el orden de implementación.

## Principios no negociables (aplican desde ya, aunque la infraestructura completa no exista)

1. **Ningún modelo ni feature entra a producción sin demostrar, mediante backtesting temporal y datos fuera de muestra, que aporta información adicional.** No se combinan modelos ni se agregan features "porque existen" (ya vigente vía ADR-0006/0007, se reafirma explícitamente para todo el catálogo de técnicas de la Sección de abajo).
2. **Las predicciones de terceros (incluyendo el endpoint `predictions` que API-Football expone) nunca sustituyen al motor propio ni se usan como feature de entrenamiento**, salvo un experimento de benchmarking explícito y documentado como tal (mismo tratamiento que las cuotas de bookmaker, ADR-0003) — nunca en el pipeline de producción por defecto.
3. **Aprendizaje continuo ≠ aprendizaje ciego.** Todo reentrenamiento o ajuste de pesos de ensemble debe respetar: ventanas temporales / walk-forward validation, holdout nunca tocado durante selección, tamaño mínimo de muestra antes de actuar sobre una señal, y controles estadísticos de significancia — nunca reaccionar a una racha corta de resultados.
4. **Todo cambio de producción debe ser reproducible, auditable y reversible.** Cada promoción/rechazo de un challenger queda registrada con su razón (extiende ADR-0008: los mismos principios de inmutabilidad y trazabilidad aplican a las decisiones de promoción, no solo a las predicciones).
5. **Separación estricta de capas** (11 responsabilidades, ver más abajo) — un componente de una capa no debe asumir responsabilidades de otra sin pasar por sus controles (p.ej., el motor de features nunca decide por sí mismo promover un modelo).
6. **La estrategia financiera (value betting, Kelly, staking, CLV, hedging, arbitraje) permanece siempre separada del motor que estima probabilidades** (ya vigente, Sección 24 del brief original / roadmap "Después de V1" — se reafirma aquí como principio arquitectónico permanente, no solo de scope de producto).

## Las 11 capas (separación de responsabilidades objetivo)

1. Adquisición de datos
2. Feature engineering
3. Modelos predictivos (individuales, de distintas familias)
4. Calibración
5. Ensemble / meta-modelo
6. Evaluación / backtesting
7. Experimentación / research
8. Model registry / versionado
9. Monitorización
10. Aprendizaje continuo (el "loop" que conecta 6-7-8-9 con producción)
11. Estrategia de apuestas y gestión de bankroll (siempre aislada de 1-10)

Mapeo actual contra el equipo de agentes de ADR-0005 (7 especialistas): hoy cubrimos 1 (Data & Backend Platform), 2-3 (Modeling & Feature Engineering, fusionados por ahora), 4+6 (Evaluation & Calibration), 9 (DevOps/MLOps), más QA & Data Integrity como función transversal. **Las capas 5 (ensemble/meta-modelo), 7 (experimentación) y 10 (aprendizaje continuo) todavía no tienen un agente dedicado** — se agregan cuando el roadmap llegue a esa etapa (ver "Próximos ADRs" abajo), fusionándolos con agentes existentes si el volumen de trabajo no justifica separarlos, siguiendo el mismo criterio de minimización de ADR-0005.

## Familias de modelos candidatas a evaluar (ninguna aprobada de antemano)

Estadísticos/probabilísticos: Poisson, Dixon-Coles, Poisson bivariada, Binomial Negativa, modelos bayesianos jerárquicos, survival analysis, modelos temporales.
Ratings: Elo, Glicko, TrueSkill, variantes propias.
ML clásico: regresión logística, Random Forest, XGBoost, LightGBM, CatBoost, SVM.
Redes neuronales: solo si volumen/calidad de datos lo justifica empíricamente (se mantiene la prohibición de ADR-0006 de usarlas "porque sí").
Métricas avanzadas: xG, xGA, xA y derivados, cuando haya una fuente confiable (pendiente evaluar en Fase 6+, ver ADR-0003 sobre cobertura de xG en API-Football).
Combinación: ensembles, stacking, blending, dynamic weighting, mixture-of-experts, meta-learning.

## Esquema Champion/Challenger (diseño objetivo, no implementado aún)

- **Champion:** el modelo/ensemble con `model_versions.status = 'production'` (mismo campo que ya existe desde Fase 4 — "champion" es el nombre de producto para lo que el esquema ya llama `production`, no requiere cambio de esquema hoy).
- **Challengers:** cualquier `model_versions.status = 'candidate'` que se esté comparando activamente contra el champion.
- Un challenger reemplaza al champion solo si Evaluation & Calibration Agent certifica mejora reproducible sin degradar calibración/robustez/estabilidad (extiende, no reemplaza, la regla de promoción de ADR-0007).
- Rollback: dado que `model_versions` nunca se borra (solo `status` cambia y hay `promoted_at`), volver a un champion anterior es reasignar `status='production'` al `model_versions.id` previo — no requiere reentrenar. Esto ya es posible con el esquema actual sin cambios.

## Ciclo de retroalimentación (diseño objetivo, fases futuras)

1. Guardar predicción con probabilidades, modelo, versión, features y timestamp — **ya implementado** vía `predictions`/`feature_snapshots` (ADR-0008, Fase 3).
2. Ingerir resultado real — **ya implementado** vía `results` (Fase 2).
3-5. Comparar predicción vs. realidad, métricas segmentadas, detección de drift/degradación de calibración — corresponde a Fase 5 (Evaluación) y se extiende en fases posteriores con segmentación más fina y detección de drift (no planificado en detalle todavía).
6-9. Reentrenamiento condicionado a evidencia suficiente, generación/evaluación de challengers, comparación contra champion — formaliza y automatiza lo que ADR-0006/0007 ya exigen manualmente; la automatización es trabajo futuro, la metodología ya es vigente desde hoy.
10-13. Ajuste de pesos de ensemble/gating, versionado completo, rollback, registro de motivos de promoción/rechazo/retiro — requiere que exista un ensemble (capa 5) primero; no aplica hasta que haya más de un modelo en producción simultáneamente.

## Próximos ADRs esperados (cuando el roadmap llegue a esa etapa — no ahora)

- ADR futuro: diseño del meta-modelo/ensemble (capa 5) y su mecanismo de gating.
- ADR futuro: agente(s) de Experimentación/Research (capa 7) y su interacción con Modeling & Feature Engineering.
- ADR futuro: automatización del ciclo de aprendizaje continuo (capa 10) — triggers de reentrenamiento, criterios mínimos de muestra, detección de drift.
- ADR futuro: diseño del módulo de estrategia de apuestas (capa 11) — ya anticipado en el brief original (Sección 24) y en `docs/roadmap/ROADMAP.md` ("Después de V1").

## Estado de implementación (2026-09-19)

**Nada de esta ADR está implementado todavía**, por diseño explícito del usuario: "La Fase 4 actual debe continuar siendo de baselines... simplemente asegurate de que la arquitectura, ADRs, esquema de datos y roadmap reflejen claramente esta visión de largo plazo." Esta ADR es una restricción de diseño hacia adelante (para no tener que reconstruir el sistema), no una tarea pendiente de la Fase 5. El roadmap (`docs/roadmap/ROADMAP.md`) sigue siendo la fuente de verdad de qué se construye y en qué orden.

## Consecuencias

- Positivas: decisiones de esquema/arquitectura tomadas en Fases 2-4 (JSONB flexible en features/hyperparameters, `model_versions.status` con semántica candidate/production/retired, inmutabilidad de predicciones y snapshots) ya son compatibles con este diseño sin necesitar romper nada retroactivamente — verificado explícitamente en esta ADR.
- Negativas: el roadmap de fases posteriores a la 10 sigue sin estar detallado fase por fase (deliberado — se detalla cuando el proyecto llegue ahí, con datos reales para informar las decisiones, no especulativamente ahora).
- Trigger de revisión: cuando el roadmap agregue una fase concreta de Ensemble/Meta-modelo o de Aprendizaje Continuo, esa fase debe generar sus propios ADRs de diseño detallado, referenciando esta ADR-0009 como marco.

## Addendum (2026-09-20, ADR-0018): dos reglas adicionales para cuando esto se construya

1. **Predicciones usadas como feature de un meta-modelo deben ser out-of-fold.** Nunca entrenar un meta-modelo/ensemble con las predicciones in-sample que otro modelo generó sobre los mismos partidos con los que ese otro modelo fue entrenado — es una forma sutil pero real de leakage (el meta-modelo aprendería a confiar en un modelo base que memorizó esos partidos, no que generaliza).
2. **Experimentos propuestos por agentes (features, hiperparámetros, arquitecturas) se ejecutan en branches/worktrees aislados.** Ningún agente tiene autorización para observar que un experimento "parece bueno" y reemplazar producción directamente — el esquema Champion/Challenger de esta ADR sigue mandando: recomendación con evidencia, promoción como acción separada y explícita (ver también ADR-0014 sobre esta misma separación sin construir nada todavía).

## Fuentes

N/A — visión de producto/arquitectura proporcionada directamente por el usuario (2026-09-19), formalizada aquí para que no se pierda entre fases. Addendum del 2026-09-20 a partir de una revisión externa posterior con mérito técnico.
