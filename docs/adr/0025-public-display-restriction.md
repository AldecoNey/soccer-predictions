# ADR-0025 — Qué se puede mostrar públicamente (formaliza BDR-003 de Business)

**Estado:** Aceptada
**Fecha:** 2026-09-25
**Decide:** Product Owner (usuario), vía handoff con el equipo de negocios (sesión separada "fulbolai-business") — Tech formaliza la restricción técnica

## Contexto

Durante el handoff HANDOFF-001 (2026-09-24) se identificó que el diseño de frontend (`MASTER_ARCHITECTURE_V1.md` Sección L, todavía no construido — Fase 9 no empezó) contemplaba mostrar solo probabilidades propias, pero eso nunca fue una restricción formal — solo lo único diseñado hasta ahora. Dado que API-Football no otorga licencia de publicación de sus datos según sus términos (R-026 del `RESEARCH_LOG` de Business), esto era un riesgo real de "dar por sentado" que se podía mostrar cualquier cosa una vez que exista el frontend.

Business propuso la restricción (BDR-003, `fulbolai_business/decisions/BDR-003-public-display-restriction.md`), y los fundadores (el usuario) la aprobaron el 2026-09-25.

## Decisión

**A partir de Fase 9 (frontend público), lo único que se puede mostrar es:**

1. **Probabilidades calculadas por FulbolAI y sus metadatos** — timestamp, versión de modelo (`model_versions.id`/`git_sha`), evaluación posterior una vez jugado el partido. Esto ya es dato propio derivado, no dato crudo de terceros.
2. **Datos básicos del partido** (equipos, fecha, resultado) — **solo si provienen de una fuente cuya licencia lo permita explícitamente.** Hoy esto es un problema abierto sin resolver (ver "Qué falta" abajo).

**Explícitamente prohibido sin una excepción documentada (ADR nuevo + revisión legal):**
- Datos crudos de API-Football: alineaciones, lesiones, estadísticas de partido.
- Cuotas de bookmakers (`bookmaker_snapshots`) o cualquier comparación pública contra ellas — ya era la posición de ADR-0003/ADR-0009 para el modelo, esto lo extiende explícitamente a la interfaz pública también.

**Esto NO restringe el uso interno** (entrenamiento, features, benchmarking, captura de cuotas vía `pipelines/capture_odds_snapshot.py`) — ADR-0021 sigue vigente sin cambios. La restricción es específicamente sobre qué llega a la interfaz pública (Fase 9 en adelante).

## Qué falta (problema técnico abierto, no urgente)

Hoy **todos** los datos de partidos (equipos, fechas, resultados) vienen de API-Football — el dataset con licencia abierta (`rhinoah/futbol-argentino-data`, CC BY-SA 4.0, ver actualización de ADR-0003) **nunca se integró al pipeline**. Para cumplir el punto 2 de la decisión hay dos caminos, ninguno decidido todavía:

1. Integrar ese dataset (u otra fuente con licencia abierta) específicamente para los datos básicos que se muestran al público, con atribución visible (requisito de la licencia CC BY-SA).
2. Conseguir una opinión legal que habilite usar los datos básicos de fixtures de API-Football (equipos/fecha/resultado) públicamente, distinto de mostrar alineaciones/lesiones/stats.

**No se decide ahora** — no bloquea nada del trabajo actual (Fase 6). Se resuelve cuando el roadmap se acerque a Fase 9, con tiempo para la opinión legal que Business ya dejó pendiente.

## Consecuencias

- Positivas: evita construir el frontend (Fase 9) asumiendo por defecto que se puede mostrar cualquier dato, y protege el lanzamiento del riesgo legal ya identificado (R02 del lado de Business).
- Negativas: limita mostrar lesiones/rotaciones directamente — la encuesta de Business (customer research, no repetida acá) encontró que el 60% de los encuestados quiere ver las bajas junto a la probabilidad. Alternativa ya anotada por Business: explicarlas con texto propio (redactado por el equipo, no republicando el dato crudo) en vez de mostrar la fuente cruda.
- Trigger de revisión: licencia comercial obtenida de algún proveedor que sí autorice publicación, u opinión legal que habilite otros usos.

## Fuentes

`fulbolai_business/decisions/BDR-003-public-display-restriction.md` (fundadores, aprobado 2026-09-25). HANDOFF-001 (2026-09-24, respuesta de Tech, pregunta 7). ADR-0003 (actualización de licencia del dataset CC BY-SA).
