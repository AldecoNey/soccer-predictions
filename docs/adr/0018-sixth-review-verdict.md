# ADR-0018 — Veredicto sobre la 6ta ronda de revisión externa (arquitectura general)

**Estado:** Aceptada — mezcla de aceptaciones concretas, un rechazo razonado, y varios "ya cubierto"
**Fecha:** 2026-09-20
**Decide:** CTO/Orquestador (Claude), a partir de una revisión externa (ChatGPT, vía el usuario)

## Contexto

Sexta revisión externa, esta vez de alcance general (arquitectura, roadmap, documentación, costos, y la visión de aprendizaje continuo). Incluye además la decisión del usuario de nombrar el producto **FulbolAI** (ver ADR-0017, decisión de producto, no evaluada aquí).

## Aceptado

- **Corrección del criterio de finalización de Fase 5 y Fase 6** (`docs/roadmap/ROADMAP.md`): exigir que "al menos un modelo/señal mejore" como condición de cierre de fase incentiva seguir probando hasta encontrar una mejora por azar — exactamente el mismo riesgo de metric-shopping que ya se había corregido en `.claude/agents/modeling-feature-engineering.md` en la ronda 1, aplicado acá al nivel de roadmap. Corregido: el criterio ahora es que la evaluación se haya hecho rigurosamente y su resultado (positivo o negativo) quede documentado — no que el resultado sea positivo.
- **`ModelVersion` de regresión logística ahora es realmente reproducible**: se registraba una fila describiendo el experimento, pero el `scaler`/`LogisticRegression` ajustados se descartaban al terminar el proceso — no había nada que cargar después para repetir la inferencia. Corregido: `logistic.serialize_fitted()`/`deserialize_fitted()` (pickle+base64, sin necesitar un artifact store dedicado, objetos chicos) serializa el modelo del último fold (el de más datos de entrenamiento) dentro de `hyperparameters`. Test de roundtrip verifica que las predicciones son idénticas tras serializar/deserializar.
- **Caveat de `rotation_index` documentado, no re-corrido**: `_safe()` convierte `rotation_index=None` (alineación insuficiente) en `0.0` (mismo valor que "sin rotación real"), lo cual conflacta dos cosas distintas. Es una crítica metodológica válida. No se repitió el experimento con una muestra estrictamente filtrada por dos razones: (1) el experimento en curso ya venía mostrando "sin mejora clara" en los primeros folds, así que una versión más estricta no cambiaría la decisión práctica; (2) matarlo a mitad de camino desperdicia el trabajo ya hecho (folds 1-3 completos al momento de esta ADR). Se deja como nota explícita en ADR-0011 y como candidato concreto si se decide invertir más en esta señal específica más adelante.
- **Definición explícita de 1-X-2**: FulbolAI define el resultado 1-X-2 como el marcador al final del **tiempo reglamentario + descuento**, excluyendo prórroga/penales. Hoy esto no afecta ningún dato real (Liga Profesional Argentina es formato liga, sin prórroga en fase regular — verificado que no hay partidos con status distinto de finished/scheduled en los datos ya cargados, aunque no se re-verificó específicamente contra el status crudo AET/PEN del proveedor). Los campos (`score_90`, `score_extra_time`, `penalties_*`) para cuando se agreguen copas ya estaban correctamente deferidos en ADR-0013 — esta ADR solo fija la definición semántica por escrito, no adelanta la implementación.
- **Refinamientos a la visión de ADR-0009** (aprendizaje continuo): se incorporan dos reglas nuevas al marco ya aceptado, sin autorizar construir nada todavía:
  1. Las predicciones de un modelo usadas como feature de un meta-modelo deben ser **out-of-fold** — nunca entrenar un meta-modelo con predicciones in-sample que otro modelo generó sobre los mismos partidos con los que fue entrenado (leakage sutil pero real).
  2. Los agentes que propongan features/hiperparámetros/arquitecturas experimentales lo harán en **branches/worktrees aislados** — ningún agente tiene autorización para observar que un experimento "parece bueno" y reemplazar producción directamente.
- **README actualizado**: decía "Fase 0 completada" y "backend/frontend/pipelines a crear en Fase 1" — completamente desactualizado (vamos por Fase 6). Corregido con el estado real.

## Rechazado con razonamiento (no solo "prematuro")

**Dixon-Coles: "la likelihood debe rechazar/penalizar tau inválido en vez de repararlo después."** La ronda 4 ya agregó `max(tau, 1e-10)` en el entrenamiento y clipping + validación en `predict_proba()` (ronda 4/ADR-0014). Esta ronda pide ir más lejos: que el objetivo de entrenamiento explícitamente penalice/rechace regiones de parámetros con `tau<0`, no solo evite `NaN`.

**Análisis:** `max(tau, 1e-10)` ya es, en la práctica, una penalización severa — cuando `tau` de la observación real es negativo, la probabilidad asignada a lo que efectivamente pasó cae a `~1e-10`, y su contribución al log-likelihood es `ln(1e-10) ≈ -23`, un castigo enorme comparado con cualquier ajuste razonable. El optimizador ya tiene un gradiente fuerte empujándolo lejos de esas regiones — no se está "validando como buenos" esos parámetros, se los está castigando casi al máximo posible dentro de un objetivo continuo. Agregar una penalización explícita adicional no cambiaría el comportamiento práctico del optimizador de forma perceptible, y si el objetivo fuera "rechazar" (no solo penalizar) esas regiones, la función dejaría de ser diferenciable donde más importa, complicando la optimización sin beneficio claro. **Se rechaza esta corrección específica** — no porque sea prematura, sino porque el mecanismo actual ya cumple la función que se pide, con una implementación más simple.

## Ya cubierto por ADRs anteriores (sin acción nueva)

- Raw ingestion layer + Cloudflare R2 (provenance completo, requests/responses crudos) — misma categoría que ADR-0013 ya rechazó (`raw immutable ingestion`), con el mismo trigger ("cuando la ingesta pase a ser continua/en vivo"). No se verificó el pricing de R2 citado por no ser una decisión que se vaya a tomar ahora.
- `match_schedule_history` — ADR-0013 la rechazó con trigger explícito "Fase 7". El review dice que "ya llegamos a Fase 7" — **no es cierto todavía**: seguimos en Fase 6 (el experimento de `rotation_index` recién está terminando). Se reevalúa cuando Fase 6 cierre y arranque Fase 7 de verdad, no antes.
- `dataset_manifest → training_run → model_artifact → evaluation_run → promotion_decision`, el resto de la cadena de continuous learning — ya es la visión de ADR-0009, ya deferida con el mismo criterio en ADR-0013/0014.
- `uv` + lockfile en vez de `requirements.txt` — mejora de higiene de dependencias razonable, pero sin urgencia (nada se ha roto por esto todavía) — se evalúa cuando el proyecto empiece a acumular más dependencias o justo antes de almacenar artifacts realmente promocionables a producción.
- Costos de Render pago para beta pública ($7/mes) — correcto como estimación, pero es una decisión de gasto futura (Fase 8+, lanzamiento) que requiere aprobación explícita del usuario en su momento, no una acción de hoy.
- Consolidación completa de `MASTER_ARCHITECTURE_V1.md`/`schema.md` — el README ya se actualizó en esta ronda; el resto de la documentación queda como deuda reconocida para la próxima sesión de trabajo dedicada a documentación, no se reescribe completa en esta misma respuesta dado el volumen ya cubierto en esta sesión.

## Consecuencias

- Positivas: el criterio de roadmap corregido es, en retrospectiva, el cambio de mayor impacto de esta ronda — evita que las próximas fases experimentales se autoengañen sobre qué cuenta como "éxito".
- Negativas: la documentación de arquitectura de alto nivel (Master doc, schema.md) sigue desactualizada — riesgo reconocido, no resuelto en esta ADR.
- Trigger de revisión: cuando arranque Fase 7 de verdad, revisar `match_schedule_history` y la capa de ingesta prospectiva (odds/lineups snapshots) como corresponde a esa fase.

## Fuentes

Decisión directa del usuario sobre el nombre "FulbolAI" (ADR-0017). Análisis matemático propio sobre el comportamiento de `max(tau, 1e-10)` como mecanismo de penalización (no se citó una fuente externa — es cálculo directo sobre la función de log-verosimilitud ya implementada en `app/prediction_models/poisson_dixon_coles.py`).
