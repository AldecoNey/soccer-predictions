# ADR-0020 — Jerarquía de fuentes (Nivel A-E) para el Football Intelligence Agent

**Estado:** Aceptada
**Fecha:** 2026-09-21
**Decide:** CTO/Orquestador (Claude)

## Contexto

`.claude/agents/football-intelligence.md` exige clasificar cada hecho cualitativo (lesión, rotación, cambio de DT, noticia) según una "jerarquía de fuentes Nivel A-E", citada como definida en la "Sección 10 del brief" original del usuario. Al ir a activar el agente (Fase 6), se verificó que esa jerarquía **nunca quedó documentada en el repo con fuentes reales** — solo existe como referencia abstracta en `MASTER_ARCHITECTURE_V1.md` y el propio agente. Sin una jerarquía concreta, el agente no tiene con qué clasificar nada, y clasificar sobre la marcha sin criterio escrito es exactamente el tipo de decisión no auditable que el principio fundamental de CLAUDE.md prohíbe para probabilidades — el mismo estándar aplica acá para no dejarlo librado a criterio implícito de una corrida a otra.

Se investigó en la web (2026-09-21) para no inventar la jerarquía. Restricción de presupuesto: la extracción debe seguir costando ~$0/mes (dentro del techo de $30/mes ya comprometido en su mayoría a API-Football Pro), así que se evaluó explícitamente si existe una alternativa de API paga de lesiones para fútbol argentino antes de asumir que WebSearch/WebFetch manual es la única vía.

## Opciones consideradas

1. **API estructurada de lesiones/rotaciones para Argentina** — descartada: no se encontró ninguna API de este tipo a precio razonable para Liga Profesional Argentina (las que existen a precio accesible cubren ligas europeas, no Argentina). No es una opción real hoy, no un rechazo por preferencia.
2. **Sin jerarquía explícita, todas las fuentes tratadas igual** — descartada: contradice directamente el diseño ya escrito del agente y el principio de auditabilidad; una noticia de un club oficial y un rumor de Twitter no pueden pesar lo mismo sin que quede documentado por qué.
3. **Jerarquía de 5 niveles con fuentes reales nombradas, investigada vía web** (elegida) — permite que el agente clasifique de forma consistente y auditable, usando WebSearch/WebFetch a demanda (sin costo adicional, sin API), consistente con cómo el agente ya estaba diseñado para operar.

## Decisión

Se adopta la siguiente jerarquía para clasificar hechos sobre Liga Profesional Argentina:

- **Nivel A — Oficial/verificado directo:** cuenta oficial del club (sitio web, X/Instagram — comunicados de parte médica o convocatoria) y AFA/Liga Profesional (afa.com.ar, ligaprofesional.ar) para fixture, sanciones del Tribunal de Disciplina y resultados oficiales. **Importante:** AFA no publica lesiones — esa información médica solo la confirma el propio club. Nivel A es siempre la fuente primaria, sin intermediario.
- **Nivel B — Periodistas credenciados especializados:** ej. César Luis Merlo (especialista en mercado de pases, ex Olé/TyC), Gastón Edul (TyC Sports, cobertura diaria de clubes/selección). Reconocidos institucionalmente por su rol y trayectoria; no se verificó de forma independiente un track record cuantitativo de precisión — se documenta esta limitación explícitamente, no se presenta como hecho verificado.
- **Nivel C — Medios establecidos:** TyC Sports, Olé, ESPN Argentina — desks editoriales con fuentes propias, sin la trazabilidad directa de A/B.
- **Nivel D — Agregadores:** Doble Amarilla, Bolavip, Fichajes.com (tiene sección específica de sancionados/lesionados por liga) — republican de otras fuentes; nunca la única fuente de un hecho, sirven como respaldo/corroboración.
- **Nivel E — No verificado:** redes sociales de hinchas, foros, rumores sin atribución clara. Se registra solo si corrobora o contradice algo de nivel superior — nunca como hecho autónomo (ver regla de "marcar contradicciones sin resolver" del agente).

**Modo de acceso:** ninguna de estas fuentes tiene API pública estructurada — confirma que el diseño ya existente del agente (WebSearch/WebFetch puntual al investigar un partido, no un scraper programado) es el correcto, no una limitación pendiente de resolver. Al ser lectura puntual equivalente a un humano navegando (no scraping masivo programado), el riesgo de ToS es categóricamente distinto del caso SofaScore/FBref ya descartado en ADR-0003 — pero la búsqueda de ToS específico de estos sitios fue **no concluyente** (no se encontró prohibición explícita, tampoco se verificó exhaustivamente); si en el futuro esto se automatiza en volumen (ej. corrida programada sin supervisión), revisar ToS de cada fuente en ese momento, no asumir que el mismo análisis sigue aplicando.

Estos 5 niveles son los valores válidos para `data_sources.reliability_level` en el esquema implementado por la tarea paralela de Data & Backend Platform Agent (ver commit de esa tarea).

## Consecuencias

- Positivas: el agente tiene ahora un criterio escrito y citable para clasificar cada hecho, en vez de un criterio implícito distinto en cada corrida. Costo $0 adicional, consistente con el presupuesto.
- Negativas / deuda técnica aceptada: la ubicación de Merlo/Edul en Nivel B se basa en reconocimiento institucional, no en un análisis cuantitativo de aciertos históricos — si en la práctica se observan errores sistemáticos de una fuente Nivel B, bajarla de nivel explícitamente en una ADR nueva, no silenciosamente. El chequeo de ToS de TyC/Olé/Fichajes.com fue no concluyente, no "verificado sin restricciones".
- Trigger de revisión: (a) si se automatiza la extracción en volumen/sin supervisión humana, revisar ToS real de cada fuente antes; (b) si aparece una API de lesiones para Argentina a precio razonable, reevaluar si reemplaza o complementa el Nivel A/B; (c) si se observa un patrón de imprecisión en una fuente de Nivel B, reclasificar con evidencia documentada.

## Fuentes

- [AFA oficial](https://www.afa.com.ar/es/) — accedido 2026-09-21.
- [Liga Profesional oficial](https://www.ligaprofesional.ar/) — accedido 2026-09-21.
- [Urban Pitch — perfil de César Luis Merlo](https://urbanpitch.com/im-not-worried-about-being-first-im-worried-about-being-right-cesar-luis-merlo-on-journalism-trust-and-transfers/) — accedido 2026-09-21.
- [Fichajes.com — sección Argentina/Primera División](https://www.fichajes.com/argentina/primera-division/jugadores) — accedido 2026-09-21.
- Búsqueda de API de lesiones para fútbol argentino a precio accesible: sin resultado — se documenta la ausencia explícitamente en vez de asumir que existe.
