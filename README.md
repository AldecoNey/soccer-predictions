# FulbolAI

Plataforma de predicción probabilística de partidos de fútbol, comenzando por la Primera División Argentina (Liga Profesional). El objetivo es la calidad, transparencia y precisión estadística de las predicciones — no recomendaciones de apuestas.

**Estado actual (2026-09-20):** Fase 6 en curso (datos contextuales — evaluando si `rotation_index` aporta señal real). Completadas: Fase 0 (arquitectura), Fase 1 (infraestructura: repo, CI, Neon, Vercel), Fase 2 (ingesta histórica: 2342 partidos, 5 temporadas 2022-2026), Fase 3 (features con anti-leakage), Fase 4 (3 baselines entrenados), Fase 5 (evaluación walk-forward — ningún baseline sin ajustar superó a naive; Elo ajustado sí lo supera en un fold, ver ADR-0010). Ver `docs/roadmap/ROADMAP.md` para el detalle fase por fase y `docs/adr/` para el registro completo de decisiones (17+ ADRs al momento de escribir esto).

## Cómo está organizado este repositorio

- `CLAUDE.md` — instrucciones persistentes para cualquier sesión de Claude Code que trabaje aquí. Léelo primero.
- `docs/architecture/` — documento maestro de arquitectura (nota: se actualiza con menor frecuencia que el código — para el estado real, `docs/roadmap/ROADMAP.md` y los ADRs más recientes son la fuente de verdad).
- `docs/adr/` — Architecture Decision Records: por qué se tomó cada decisión técnica importante, en orden cronológico.
- `docs/roadmap/` — plan de fases del proyecto y su estado real.
- `docs/data/` — modelo de datos (ver también `backend/app/models.py` como fuente de verdad del esquema real).
- `.claude/agents/` — definición de los agentes especializados.
- `.claude/rules/` — reglas cargadas automáticamente por Claude Code según los archivos que se estén tocando (ej. integridad temporal/anti-leakage).
- `backend/` — API (FastAPI), pipelines de datos/modelado (Python), tests.
- `frontend/` — interfaz web (Next.js), todavía esqueleto sin conectar a datos reales.

## Principio de diseño central

Las probabilidades finales siempre provienen de modelos cuantitativos reproducibles y auditables (Elo, Poisson/Dixon-Coles, y candidatos más complejos solo si demuestran mejora medible) — nunca de un ajuste arbitrario de un modelo de lenguaje. Ver ADR-0006 y ADR-0007.

## Presupuesto

Máximo USD 30/mes combinando datos + hosting. Actualmente ~$19-26/mes (API-Football Pro $19 + hosting, ver ADR-0002/0003/0017 y sección de costos del documento maestro).
