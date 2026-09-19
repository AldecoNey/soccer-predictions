# ADR-0005 — Arquitectura multiagente mínima

**Estado:** Aceptada
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude)

## Contexto

El brief original propone hasta 10 roles especializados (Data Acquisition, Data Quality/Provenance, Football Intelligence, Feature Engineering, Modeling, Evaluation & Calibration, Backend/Data Platform, Frontend/Product, QA/Review, DevOps/MLOps) más un Orquestador. El principio explícito es "crear la menor cantidad de agentes necesaria para obtener especialización real" — no crear agentes para aparentar sofisticación.

## Análisis

Evalué qué roles comparten el mismo tipo de trabajo diario, las mismas herramientas y el mismo tipo de error a vigilar, para decidir cuáles fusionar:

- **Data Acquisition + Backend/Data Platform:** ambos son "ingeniería de plomería" — conectar APIs externas, diseñar el esquema de BD, construir la capa de acceso a datos y los pipelines. A la escala de una sola liga con una fuente primaria (ADR-0003), separarlos crearía una frontera artificial. → **Fusionados.**
- **Data Quality/Provenance + QA/Review:** ambos son funciones de verificación independientes de quien construye — code review, tests, detección de leakage, y validación de calidad/procedencia de datos son la misma disciplina de "¿esto es correcto y confiable?". Mantenerlos separados de quienes acumulan los datos y el código preserva objetividad. → **Fusionados** en "QA & Data Integrity".
- **Feature Engineering + Modeling:** en un equipo pequeño, iterar features y modelos es un ciclo acoplado (una feature nueva casi siempre nace para mejorar un modelo específico, y se descarta según el mismo backtesting). Separarlos obligaría a una coordinación constante sin beneficio real de objetividad (a diferencia de Evaluation, que sí debe ser independiente del Modeling para no "calificarse a sí mismo"). → **Fusionados.**
- **Evaluation & Calibration:** se mantiene **separado** de Modeling deliberadamente. Es la función que decide si un modelo nuevo reemplaza al desplegado; si la misma entidad que entrena también evalúa, hay riesgo de sesgo de confirmación. Este es el único caso donde la independencia entre agentes importa más que la eficiencia de fusionar.
- **Football Intelligence:** se mantiene separado porque requiere una competencia distinta (dominio futbolístico + jerarquía de fuentes + estructuración de señales cualitativas) que no se solapa con ingeniería de datos ni con modelado.
- **Frontend/Product:** se mantiene separado, sin solapamiento de herramientas ni de tipo de trabajo con el resto.
- **DevOps/MLOps:** se mantiene separado — scheduling, monitoreo y alertas es una disciplina distinta y transversal a todo lo demás, con su propio checklist (ver `.claude/agents/devops-mlops.md`).

## Decisión

Equipo final: **1 orquestador + 6 agentes especializados** (bajado de 10+1):

1. **Orquestador/CTO** — es la sesión principal de Claude Code, guiada por `CLAUDE.md`. No es un subagente independiente; mantiene visión global, divide trabajo, aprueba integraciones y es quien interactúa con el usuario.
2. **Data & Backend Platform Agent** (`.claude/agents/data-backend-platform.md`) — conectores a fuentes externas, esquema de BD, API, pipelines de ingesta.
3. **Football Intelligence Agent** (`.claude/agents/football-intelligence.md`) — señales cualitativas, jerarquía de fuentes, estructuración de contexto (lesiones, rotaciones, etc.).
4. **Modeling & Feature Engineering Agent** (`.claude/agents/modeling-feature-engineering.md`) — features reproducibles, baselines, modelos candidatos, ensembles.
5. **Evaluation & Calibration Agent** (`.claude/agents/evaluation-calibration.md`) — backtesting, métricas de calibración, comparación de versiones, benchmark vs. mercado. Independiente del anterior por diseño.
6. **Frontend/Product Agent** (`.claude/agents/frontend-product.md`) — interfaz web MVP.
7. **QA & Data Integrity Agent** (`.claude/agents/qa-data-integrity.md`) — revisión de código, tests, detección de leakage, validación de calidad/procedencia de datos, regresiones.
8. **DevOps/MLOps Agent** (`.claude/agents/devops-mlops.md`) — scheduling, despliegue, logging, monitoreo, alertas.

(Nota: 7 especialistas, no 6 — al escribir la fusión resultaron 7 roles finales tras separar correctamente Evaluation de Modeling. Sigue siendo una reducción significativa desde los 10 originales.)

## Nota de evolución futura (ADR-0009)

Este equipo de 7 especialistas cubre las capas 1-4, 6 y 9 de la arquitectura evolutiva descrita en ADR-0009 (adquisición, features, modelos, calibración, evaluación, monitorización), más QA como función transversal. Las capas 5 (ensemble/meta-modelo), 7 (experimentación/research) y 10 (aprendizaje continuo automatizado) todavía no tienen agente dedicado — se evalúa agregarlos (o fusionarlos con los existentes, siguiendo el mismo criterio de minimización de esta ADR) recién cuando el roadmap llegue a esa etapa, no antes.

## Consecuencias

- Positivas: menos fronteras de coordinación, menos overhead de "traducir" contexto entre agentes, más fácil de mantener para un product owner de nivel técnico básico.
- Negativas: si el proyecto escala mucho (más ligas, más volumen de datos), Data & Backend Platform podría saturarse y requerir separar de nuevo Data Acquisition — se documenta como trigger de revisión.
- Trigger de revisión: cuando se agregue la segunda competición (Copa Argentina u otra), reevaluar si Data & Backend Platform sigue siendo manejable como un solo rol.

## Fuentes

N/A — decisión de diseño organizacional basada en el brief del usuario y análisis de solapamiento de responsabilidades.
