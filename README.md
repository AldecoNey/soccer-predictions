# Sistema Multiagente de Pronósticos de Fútbol

Plataforma de predicción probabilística de partidos de fútbol, comenzando por la Primera División Argentina (Liga Profesional). El objetivo es la calidad, transparencia y precisión estadística de las predicciones — no recomendaciones de apuestas.

**Estado actual:** Fase 0 (arquitectura y decisiones) completada. Ver `docs/architecture/MASTER_ARCHITECTURE_V1.md` para el documento maestro y `docs/roadmap/ROADMAP.md` para las fases siguientes.

## Cómo está organizado este repositorio

- `CLAUDE.md` — instrucciones persistentes para cualquier sesión de Claude Code que trabaje aquí. Léelo primero.
- `docs/architecture/` — documento maestro de arquitectura.
- `docs/adr/` — Architecture Decision Records: por qué se tomó cada decisión técnica importante.
- `docs/roadmap/` — plan de fases del proyecto.
- `docs/data/` — modelo de datos vigente.
- `.claude/agents/` — definición de los agentes especializados (data/backend, football intelligence, modeling, evaluation, frontend, QA, devops).
- `backend/`, `frontend/`, `pipelines/` — código de la aplicación (a crear en Fase 1).

## Principio de diseño central

Las probabilidades finales siempre provienen de modelos cuantitativos reproducibles y auditables (Elo, Poisson/Dixon-Coles, y candidatos más complejos solo si demuestran mejora medible) — nunca de un ajuste arbitrario de un modelo de lenguaje. Ver ADR-0006 y ADR-0007.

## Presupuesto

Máximo USD 30/mes combinando datos + hosting. Ver ADR-0002 y ADR-0003 para el desglose actual (~$0/mes en el arranque).

