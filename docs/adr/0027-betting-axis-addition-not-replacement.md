# ADR-0027 — Eje de apuestas (BDR-005): agregado al diseño existente, no un reemplazo

**Estado:** Aceptada
**Fecha:** 2026-09-25
**Decide:** Product Owner (usuario), confirmación directa

## Contexto

Business reportó (BDR-005, `fulbolai_business/decisions/BDR-005-positioning-axes-ai-football-betting.md`) que los fundadores definieron "IA + fútbol + apuestas" como ejes de marca, con features concretas propuestas para Fase 9 (cuota justa, calculadora de margen, señales de valor condicionadas). Esto toca directamente la regla no negociable de `CLAUDE.md` ("Alcance del MVP": no agregar funcionalidades de apuestas/value betting sin aprobación explícita del usuario) — se le pidió confirmación directa al usuario antes de tratarlo como aprobado, en vez de aceptarlo solo porque llegó relayado por la sesión de negocios.

**El usuario confirmó explícitamente (2026-09-25): esto es un agregado al diseño ya existente, no un cambio.** El MVP original (Liga Profesional Argentina, motor de predicción cuantitativo, principio fundamental de que ningún LLM decide una probabilidad por criterio propio) no se toca ni se reinterpreta.

## Decisión

**Se aprueba el eje de apuestas como adición, con estas condiciones explícitas y no negociables:**

1. **El MVP y sus reglas estructurales no cambian.** Sigue siendo solo Liga Profesional Argentina, el motor de predicción sigue siendo 100% cuantitativo/reproducible (regla del "Principio fundamental" de `CLAUDE.md`, sin excepción), y todas las reglas 1-8 de `CLAUDE.md` siguen vigentes sin modificación.
2. **Todo lo que se agrega está gateado detrás de ADR-0026** (umbral de calidad para publicar) y **no antes de Fase 9** (frontend público) — nada de esto se construye ahora.
3. **Features concretas ya aprobadas para cuando llegue ese momento:**
   - **"Cuota justa"** = 1 ÷ probabilidad propia del modelo. Es una transformación matemática de nuestro propio dato derivado — no usa ni redistribuye datos de terceros, no toca ADR-0025.
   - **Calculadora de margen**: el usuario ingresa la cuota de SU casa de apuestas, la calculadora computa probabilidad implícita/margen/diferencia contra nuestro modelo. No usa ningún dato de terceros (la cuota la tipea el usuario) — no toca ADR-0025 ni requiere licencia de nadie.
4. **Lo que NO cambia (reafirmado explícitamente):** ADR-0025 sigue vigente sin excepción — nunca se muestran cuotas de API-Football ni ningún dato crudo de terceros. "Señales de valor" (`hay valor en X`) quedan condicionadas a un gate todavía no cerrado (respuesta técnica preparatoria ya enviada en HANDOFF-003, pendiente de que Business confirme los números antes de que sea una decisión final).
5. **Leyendas obligatorias** ("+18", advertencia de juego compulsivo) en cualquier superficie que mencione apostar — requisito de Business, no negociable de este lado tampoco.

## Consecuencias

- Positivas: la dirección de producto queda clara para cuando el roadmap llegue a Fase 9, sin que nadie tenga que adivinar o dar por sentado algo más adelante (mismo espíritu que ADR-0025).
- Negativas: ninguna sobre el trabajo actual — no cambia nada de Fase 6 en curso.
- Trigger de revisión: si en algún momento se propusiera algo que SÍ requiera datos de terceros (cuotas de API-Football, predicciones ajenas) para estas features, eso sí sería un cambio real que necesitaría su propio ADR y aprobación explícita — no se cuela por extensión de este.

## Fuentes

Confirmación directa del usuario, 2026-09-25, en esta sesión. `fulbolai_business/decisions/BDR-005-positioning-axes-ai-football-betting.md`.
