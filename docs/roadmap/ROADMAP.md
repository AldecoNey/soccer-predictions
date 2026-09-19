# Roadmap técnico — V1 (Primera División Argentina)

Cada fase tiene objetivo, tareas, agente responsable, entregables, tests y criterio de finalización. No se avanza a la fase siguiente si el criterio de finalización de la actual no se cumple (Sección 31 del brief). Progreso real se rastrea en las tasks de cada sesión de trabajo, no en este documento — este roadmap es el plan, no el estado.

## Fase 0 — Investigación y decisiones (EN CURSO)

- **Objetivo:** cerrar las decisiones de arquitectura antes de escribir código de producto.
- **Tareas:** investigación de fuentes de datos (hecho, ADR-0003), investigación de hosting (hecho, ADR-0002), verificar cobertura real de The Odds API para Liga Profesional Argentina (pendiente), confirmar límites reales de API-Football con una cuenta de prueba.
- **Agente responsable:** Orquestador + Data & Backend Platform Agent.
- **Entregables:** este documento, ADRs 0001-0008, `CLAUDE.md`, `.claude/agents/*.md`.
- **Tests:** N/A (fase documental).
- **Criterio de finalización:** documento maestro aprobado por el usuario; decisiones de la Sección "Decisiones para el usuario" resueltas.

## Fase 1 — Infraestructura base ✅ COMPLETADA (2026-09-19)

- **Resultado:** repo público en https://github.com/AldecoNey/soccer-predictions · CI verde (backend+frontend) · workflow programado verificado (`scheduled-hello-world.yml`) · Neon (Postgres 18.6) conectado y verificado vía `backend/scripts/check_db_connection.py` · frontend Next.js desplegado en Vercel (https://frontend-ibbt2pj85-ney22.vercel.app), deploy automático en cada push a `main`, protección SSO por defecto desactivada para que sea público.
- **Objetivo:** repositorio ejecutable de extremo a extremo aunque no haga nada útil todavía (esqueleto).
- **Tareas:** estructura de carpetas del código (`backend/`, `frontend/`, `pipelines/`), entorno Python con `pyproject.toml`/`requirements.txt`, `.env.example`, conexión a Neon (Postgres) verificada, proyecto Vercel enlazado, primer workflow de GitHub Actions "hello world" con schedule.
- **Agente responsable:** Data & Backend Platform Agent + DevOps/MLOps Agent.
- **Entregables:** repo con CI mínimo corriendo, conexión a BD verificada.
- **Tests:** test de conexión a BD, lint/format configurado (ruff/black), CI verde en GitHub Actions.
- **Criterio de finalización:** un `git push` dispara CI, y un workflow programado corre exitosamente al menos una vez.

## Fase 2 — Pipeline de ingesta de datos ✅ COMPLETADA (2026-09-19)

- **Resultado:** conector a API-Football (`backend/app/external/api_football.py`) + pipeline idempotente (`backend/pipelines/ingest_historical_fixtures.py`) corrido contra las 3 temporadas disponibles en el plan Free (2022-2024, ver ADR-0003 — 2025/2026 están bloqueadas por el proveedor a nivel de plan). Resultado en Neon: 1 competición, 3 temporadas, 32 equipos, 1337 partidos, 1337 resultados. Verificado: cero duplicados al re-ingerir (upsert por `api_football_id`), distribución de resultados plausible (43.8% local / 24.4% visitante / 31.8% empate). No se usó el dataset `rhinoah/futbol-argentino-data` como bootstrap adicional porque API-Football ya cubrió 3 temporadas completas por sí sola — se deja como fuente de respaldo si hace falta más histórico.
- **Objetivo:** traer fixtures, resultados y equipos reales de Liga Profesional Argentina a la BD.
- **Tareas:** conector a API-Football, mapeo de `external_ids`, carga de `competitions`/`seasons`/`teams`/`matches`, importación del dataset histórico `rhinoah/futbol-argentino-data` para bootstrap, validación cruzada entre ambas fuentes.
- **Agente responsable:** Data & Backend Platform Agent. Revisión: QA & Data Integrity Agent.
- **Entregables:** BD poblada con al menos 2 temporadas de fixtures/resultados.
- **Tests:** tests de datos (Sección 22 del brief): sin duplicados, sin IDs inconsistentes, sin fechas imposibles, sin resultados imposibles (ej. goles negativos).
- **Criterio de finalización:** cobertura verificada de fixtures y resultados de al menos 2 temporadas completas, sin inconsistencias detectadas por los data tests.

## Fase 3 — Dataset histórico y control anti-leakage

- **Objetivo:** construir el dataset de entrenamiento respetando el corte temporal por horizonte (ADR-0007).
- **Tareas:** implementar el cálculo de features "as of" una fecha (nunca usando datos futuros a esa fecha), implementar `feature_snapshots`, implementar el checklist anti-leakage como tests automatizados.
- **Agente responsable:** Modeling & Feature Engineering Agent. Revisión: QA & Data Integrity Agent (obligatoria antes de cualquier entrenamiento).
- **Entregables:** función/pipeline `build_features(match_id, as_of_timestamp)` reproducible y testeada.
- **Tests:** model tests (Sección 22): dado un `as_of` timestamp, ningún feature generado tiene un timestamp de dato posterior; test de reproducibilidad (mismo input → mismo output).
- **Criterio de finalización:** el checklist anti-leakage de ADR-0007 pasa como suite de tests automatizada.

## Fase 4 — Baselines y primer modelo

- **Objetivo:** Baseline 0, Baseline 1 (Elo) y Baseline 2 (Poisson/Dixon-Coles) entrenados y produciendo P(local)/P(empate)/P(visitante) que suman 1.
- **Agente responsable:** Modeling & Feature Engineering Agent.
- **Entregables:** 3 modelos entrenados, versionados en `model_versions`.
- **Tests:** probabilidades entre 0 y 1, suma exactamente 1 (con tolerancia de punto flotante), reproducibilidad con seed fija.
- **Criterio de finalización:** los 3 baselines corren de punta a punta sobre el dataset histórico y generan predicciones válidas.

## Fase 5 — Evaluación y calibración

- **Objetivo:** medir rigurosamente los baselines con walk-forward validation (ADR-0007) antes de considerar modelos más complejos.
- **Agente responsable:** Evaluation & Calibration Agent (independiente del agente que entrenó los modelos).
- **Entregables:** reporte de log loss, Brier score, calibration curves y ECE por horizonte, para cada baseline.
- **Tests:** verificación de que la validación es estrictamente temporal (ningún fold usa datos futuros respecto al fold de entrenamiento correspondiente).
- **Criterio de finalización:** al menos un modelo supera al Baseline 0 de forma estadísticamente consistente en log loss a través de múltiples ventanas temporales.

## Fase 6 — Datos contextuales/cualitativos

- **Objetivo:** incorporar lesiones, rotaciones, descanso y otras señales cualitativas como features estructuradas (Sección 9 del brief).
- **Agente responsable:** Football Intelligence Agent (estructuración) + Modeling & Feature Engineering Agent (integración como features).
- **Entregables:** `player_availability`, `news_signals` poblados; features como `player_availability_score`, `rest_days`, `rotation_index` incorporadas y backtesteadas.
- **Tests:** cada feature nueva debe demostrar mejora en log loss vía backtesting antes de quedar en el modelo de producción (si no mejora, se documenta y se descarta — Sección 11 del brief sobre H2H aplica al mismo criterio para cualquier feature).
- **Criterio de finalización:** al menos una señal cualitativa demuestra aporte medible; las que no aportan quedan documentadas como descartadas (no eliminadas del código sin registro, para no repetir el experimento).

## Fase 7 — Automatización T-72/T-24/T-2

- **Objetivo:** los 3 snapshots se generan automáticamente vía GitHub Actions sin intervención manual.
- **Agente responsable:** DevOps/MLOps Agent + Data & Backend Platform Agent.
- **Entregables:** 3 workflows programados + un workflow de registro de resultados post-partido.
- **Tests:** ejecución exitosa verificada en al menos una fecha de partidos reales; alertas si un snapshot no se genera a tiempo.
- **Criterio de finalización:** un fin de semana completo de fixtures genera sus 3 snapshots automáticamente y registra resultados sin intervención manual.

## Fase 8 — Backend / API

- **Objetivo:** exponer predicciones vía API para el frontend.
- **Agente responsable:** Data & Backend Platform Agent.
- **Entregables:** endpoints FastAPI (próximos partidos, predicción con evolución de snapshots, histórico).
- **Tests:** integration tests de la API contra una BD de prueba.
- **Criterio de finalización:** API responde con datos reales, documentada vía OpenAPI.

## Fase 9 — Frontend MVP

- **Objetivo:** interfaz pública simple (Sección 20 del brief).
- **Agente responsable:** Frontend/Product Agent.
- **Entregables:** página de próximos partidos, vista de partido individual con evolución 72h/24h/2h.
- **Tests:** verificación manual en navegador (golden path + casos borde: partido sin snapshot aún, partido finalizado).
- **Criterio de finalización:** un usuario externo puede ver predicciones reales de Liga Profesional Argentina en la web desplegada.

## Fase 10 — Producción y monitoreo continuo

- **Objetivo:** el sistema corre solo, de forma confiable, con alertas ante fallas (Sección 23 del brief).
- **Agente responsable:** DevOps/MLOps Agent.
- **Entregables:** logging estructurado, alertas (fixture faltante, predicción no generada, probabilidades inválidas, fuente agotó cuota), dashboard mínimo de salud del sistema.
- **Criterio de finalización:** el sistema opera una temporada completa sin intervención manual salvo incidentes alertados explícitamente.

---

## Después de V1 (no planificado en detalle todavía)

Expansión de competiciones (Sección 25 del brief: Argentina → CONMEBOL → ligas europeas → UEFA), evaluada caso por caso contra los criterios de cobertura de datos definidos, no por defecto. Módulo de value betting (Sección 24) como proyecto separado, solo después de que el núcleo predictivo demuestre calibración sólida.
