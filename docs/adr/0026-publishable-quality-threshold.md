# ADR-0026 — Umbral mínimo de calidad para publicar predicciones (HANDOFF-002)

**Estado:** Aceptada
**Fecha:** 2026-09-25
**Decide:** Evaluation & Calibration (función) / CTO — Business aportó el criterio comercial (HANDOFF-002), Tech define métrica y método según su propio mandato

## Contexto

HANDOFF-002 (Business, 2026-09-25): la marca de FulbolAI se apoya en publicar todas las predicciones sin borrar ninguna (append-only, ADR-0008) — lo primero que se publique queda para siempre. Publicar un modelo que rinde peor que alternativas triviales sería comercialmente indefendible y, por el diseño append-only, irreversible de sacar del historial. Business fijó 4 restricciones comerciales; pidió que Tech defina métrica y método.

Contexto técnico directamente relevante, aprendido HOY mismo (ADR-0024): validar `elo_tuned` con dos folds nuevos e independientes (2025, 2026) no alcanzó para un veredicto PROMOTE — la dirección fue consistente pero el margen no fue estadísticamente distinguible de ruido en el fold más grande. Esta ADR toma esa experiencia real como evidencia de cuán estricto debe ser el umbral, no como un caso aislado.

## Restricciones comerciales de Business (HANDOFF-002)

1. No publicar un modelo que rinda peor que el baseline ingenuo out-of-sample (mínimo no negociable).
2. Preferible que supere también a Elo simple (no obligatorio).
3. No hace falta superar al consenso de bookmakers.
4. Debe estar bien calibrado — la comunicación pública dirá "de cada 10 partidos así, gana ~6", así que un modelo mal calibrado hace falso el mensaje central de la marca.

## Decisión

### 1. Métrica y margen de promoción

**Tres gates, todos obligatorios — no basta con "en promedio es mejor":**

- **Gate A (mínimo de Business):** `log_loss(candidato) < log_loss(baseline_naive)` en el agregado de evidencia nueva e independiente.
- **Gate B (consistencia entre folds):** la mejora debe sostenerse en **al menos 3 folds walk-forward independientes** (ventanas temporales que no se solapan, ninguno "gastado" en selección de hiperparámetros — mismo criterio de `.claude/rules/temporal-integrity.md`). Un solo fold (lo que pasó con `elo_tuned` en ADR-0010) no alcanza. Dos folds que no coinciden en magnitud (lo que pasó hoy en ADR-0024) tampoco.
- **Gate C (significancia estadística, no solo dirección):** la mejora agregada debe ser estadísticamente significativa — bootstrap pareado sobre la diferencia de log-loss por partido (mismo método usado en ADR-0024), intervalo de confianza 95% que **no cruce cero**. Ganar en promedio no alcanza si el intervalo de confianza incluye "podría ser cero o negativo".

**Deliberadamente sin margen fijo en porcentaje** (ej. "2% mejor que naive") — un número arbitrario no tiene fundamento estadístico. Exigir significancia real (Gate C) es más riguroso que exigir una magnitud grande que podría ser ruido de todas formas, como se vio hoy con el fold 2026 (mayor gap relativo, pero tampoco significativo al 95%).

**Elo (punto 2 de Business):** se reporta la comparación en el scorecard interno, pero no bloquea la promoción si el candidato supera a naive sin superar a Elo — es "preferible", no un gate, exactamente como lo pidió Business.

**Bookmakers (punto 3):** no se exige, consistente con el diseño ya vigente (ADR-0003/ADR-0009 — cuotas son benchmark, nunca listón de aprobación).

### 2. Calibración alcanzable

Con los datos reales de este proyecto: una temporada de Liga Profesional Argentina hoy son ~400-510 partidos (2022-2024 puro round-robin; 2025+ con playoffs, ADR-0019/0024). El ECE observado en los modelos ya evaluados (sin calibrador post-hoc todavía) anduvo en el rango 0.02-0.07 (ADR-0010: Elo 0.0189, Poisson-DC 0.0685; ADR-0024: elo_tuned 0.02-0.05 según fold).

**Propuesta (objetivo, no promesa — se confirma empíricamente cuando exista un candidato real compitiendo por promoción):**
- ECE global ≤ 0.05, consistente con lo que ya logran los baselines actuales sin ajuste dedicado — no es aspiracional sin base, es el rango ya observado.
- **Más importante para el mensaje público específico:** calibración verificada en el rango de "favorito claro" (probabilidad predicha 55-75%, el rango que literalmente se va a comunicar como "de cada 10 así, gana X") con un reliability diagram/binning dedicado a esa franja, no solo el ECE global agregado — un ECE global aceptable puede esconder mala calibración justo en el rango que se comunica. Se exige un mínimo de ~50-100 partidos cayendo en esa franja antes de confiar en el número.
- Si el candidato no cumple esto de entrada, el paso siguiente natural es un calibrador post-hoc (Platt/isotónica/temperature scaling, ajustado solo con datos de entrenamiento — ya identificado como próximo experimento en ADR-0024), no forzar la publicación igual.

### 3. Publicación silenciosa: viable, y es el camino recomendado

**Sí, técnicamente viable sin cambios de esquema** — encaja directo con el diseño append-only ya existente (ADR-0008). Una vez que exista el pipeline en vivo (Fase 7-8), las predicciones se generan y persisten normalmente (timestamp, versión de modelo), pero no se exponen en el frontend público hasta cumplir los gates de arriba. Cuando se "abre" el historial, por el mismo diseño append-only **se abre completo desde el día 1** — no se puede esconder selectivamente lo malo. Esa es justamente la garantía que hace confiable la apertura, no una limitación del enfoque.

**Aclaración honesta:** esto no adelanta CUÁNDO se puede empezar a acumular predicciones — sigue atado a que exista Fase 7 (automatización en vivo), que no empezó. Lo que sí logra es separar "empezar a construir el registro real" de "anunciarlo públicamente", que es exactamente lo que Business pidió evaluar.

### 4. Volumen para que el scorecard público sea significativo

Evidencia directa de hoy mismo (ADR-0024): un bootstrap sobre ~400-510 partidos (una temporada) no alcanzó significancia al 95% para una mejora chica (~0.1% relativo), y quedó cerca pero tampoco significativa para una mejora mayor (~0.8%). **Se propone exigir al menos 2 ventanas independientes de evidencia (~800-1000 partidos de predicciones reales ya jugadas y evaluadas)** antes de presentar el scorecard público como "estadísticamente significativo" — esto es distinto del gate de promoción del modelo (sección 1), es específicamente sobre cuándo el número que ve el público deja de ser ruido de muestra chica.

## Consecuencias

- Positivas: criterio objetivo, pre-registrado antes de tener un candidato real que lo cumpla o no — evita la tentación de ajustar el umbral después de ver un resultado (metric-shopping, el mismo riesgo que ADR-0018 ya corrigió para el cierre de fases).
- Negativas: el umbral es exigente (3 folds + significancia estadística, no solo "en promedio mejor") — probablemente retrasa la primera publicación más de lo que un criterio más laxo hubiera permitido. Aceptado explícitamente: es la contrapartida de que lo publicado quede para siempre (ADR-0008).
- Trigger de revisión: si un candidato real cumple Gate A y B pero queda al borde de Gate C repetidamente, revisar si el bootstrap pareado es el método más adecuado o si conviene un test de significancia distinto — no bajar el umbral solo porque un modelo casi lo alcanza.

## Fuentes

`fulbolai_business/shared/HANDOFF-002-publishable-quality-threshold.md` (Business, 2026-09-25). Evidencia técnica propia: ADR-0007 (jerarquía de métricas), ADR-0010 (primer intento de promoción, un solo fold insuficiente), ADR-0024 (segundo intento, bootstrap pareado real usado como método de referencia acá).
