# ADR-0001 — Usar Architecture Decision Records

**Estado:** Aceptada
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude)

## Contexto

El proyecto será construido incrementalmente por un equipo de agentes especializados dirigidos por Claude Code, con el usuario actuando como product owner de nivel técnico básico. Necesitamos un registro persistente de *por qué* se tomó cada decisión técnica relevante (base de datos, fuentes de datos, modelos, calibración, etc.), de forma que:

- futuras sesiones de Claude Code no repitan debates ya cerrados;
- el usuario pueda auditar decisiones sin releer código;
- si una decisión deja de tener sentido (cambia un precio, aparece una API mejor), se pueda revisar de forma localizada.

## Opciones consideradas

1. **ADRs en Markdown dentro del repo** — versionados con git, sin dependencias externas, legibles por agentes y humanos.
2. **Documento único de decisiones** — más simple pero no escala, difícil de referenciar individualmente.
3. **Herramienta externa (Notion, Confluence)** — fuera del control de versiones, desincronizada del código.

## Decisión

Usamos ADRs en Markdown, numerados secuencialmente, en `docs/adr/`, siguiendo la plantilla `0000-template.md`. Cada decisión técnica no trivial (stack, fuente de datos, modelo, esquema de BD, estrategia de calibración, etc.) genera un ADR nuevo. Las decisiones que solo confirman/continúan una anterior no requieren ADR nuevo, salvo que cambien la justificación.

## Consecuencias

- Positivas: trazabilidad completa, revisable en PRs, no depende de servicios externos.
- Negativas: requiere disciplina para no dejar decisiones importantes sin documentar.
- Trigger de revisión: si el volumen de ADRs crece mucho (>50), evaluar un índice categorizado en `docs/adr/README.md`.

## Fuentes

N/A — decisión de proceso.
