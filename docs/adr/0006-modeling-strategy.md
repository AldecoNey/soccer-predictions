# ADR-0006 — Estrategia de modelado: baselines antes que complejidad

**Estado:** Aceptada (la selección final de modelo queda abierta a experimentación, ver Sección G del documento maestro)
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude), validación final por Evaluation & Calibration Agent

## Contexto

El brief es explícito: "no decidas de antemano que una única técnica es la correcta" y "evita deep learning simplemente por parecer más avanzado". El criterio de selección debe ser rendimiento fuera de muestra + calibración + robustez + interpretabilidad + costo operacional, no sofisticación aparente.

## Decisión

Orden de experimentación obligatorio (no se puede saltar etapas):

1. **Baseline 0 — Ingenuo:** frecuencias históricas de 1-X-2 (sin distinguir equipos) como piso de referencia. Sirve solo para verificar que cualquier modelo real aporta algo por encima del azar informado.
2. **Baseline 1 — Fuerza relativa simple:** Elo básico (o rating equivalente) + home advantage, sin más features. Es interpretable, barato de calcular, y ya es un baseline fuerte en fútbol.
3. **Baseline 2 — Poisson / Dixon-Coles:** modelo de goles esperados por equipo (ataque/defensa) con ajuste de Dixon-Coles para la sobre-representación de empates a 0 y resultados ajustados. Es el estándar académico de referencia en modelado de fútbol y da probabilidades 1-X-2 nativas y coherentes (P(local)+P(empate)+P(visitante)=1 por construcción).
4. **Candidato 3 — Regresión logística multinomial** sobre features estructuradas (forma reciente, Elo, descanso, disponibilidad de plantel) como puente entre el rigor estadístico de Poisson/Dixon-Coles y la flexibilidad de incorporar variables contextuales (lesiones, fatiga) que Poisson puro no captura bien.
5. **Candidato 4 — Gradient boosting (LightGBM/XGBoost) calibrado:** solo si los candidatos anteriores muestran techo de rendimiento y hay suficiente volumen de datos para justificar un modelo con más parámetros, dado el riesgo de sobreajuste con el tamaño de dataset de una sola liga.
6. **Ensemble/stacking:** solo si se demuestra empíricamente que combinar 2+ modelos mejora log loss/calibración de forma consistente en validación temporal, no por defecto.

**Regla de promoción:** ningún modelo pasa a producción sin vencer al modelo actualmente desplegado (o al Baseline 1 si es el primero) en log loss y calibración, medido con validación temporal (ver ADR-0007), evaluado por el Evaluation & Calibration Agent — nunca autoevaluado por el mismo agente que lo entrenó.

**Explícitamente descartado para V1:** deep learning (redes neuronales). No hay evidencia de que aporten ventaja sobre Poisson/Dixon-Coles o GBMs bien calibrados en datasets del tamaño de una sola liga, y su interpretabilidad y costo operacional son peores.

## Consecuencias

- Positivas: cada incremento de complejidad debe justificarse con evidencia, evitando sobreajuste y facilitando explicar el sistema al usuario.
- Negativas: el desarrollo del modelo "final" toma más iteraciones que ir directo a un modelo complejo.
- Trigger de revisión: si al incorporar más ligas/temporadas el volumen de datos crece órdenes de magnitud, reevaluar si un modelo jerárquico bayesiano (que comparte fuerza estadística entre ligas) supera a modelos independientes por liga.

## Fuentes

Decisión basada en literatura estándar de modelado de fútbol (Dixon-Coles 1997 es el paper de referencia académica para este enfoque) y en el principio explícito del brief de priorizar simplicidad validada sobre sofisticación aparente.
