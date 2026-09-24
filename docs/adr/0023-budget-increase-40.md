# ADR-0023 — Aumento de presupuesto: USD 30/mes → USD 40/mes

**Estado:** Aceptada
**Fecha:** 2026-09-24
**Decide:** Product Owner (usuario)

## Contexto

El techo de $30/mes (ADR-0002/0003) era una regla no negociable desde el inicio del proyecto. Durante el handoff cruzado con el equipo de negocios (sesión separada "fulbolai-business-0c", `HANDOFF-001`), surgió una discrepancia: el usuario le había comunicado a esa sesión un techo de $40/mes, distinto del $30/mes vigente acá. Se lo señalé directamente al usuario en vez de resolverlo unilateralmente entre las dos sesiones — un aumento de presupuesto es una decisión de producto/gasto real, exactamente el tipo de cosa que CLAUDE.md exige escalar, no inferir.

## Decisión

**El usuario confirmó explícitamente: el presupuesto correcto es USD 40/mes**, no $30/mes. Se actualiza como el nuevo techo no negociable (regla 8 de `CLAUDE.md`).

No cambia ninguna decisión de gasto ya tomada — el gasto real actual sigue siendo ~$19/mes (API-Football Pro), muy por debajo tanto del techo viejo como del nuevo. El efecto práctico es que queda más margen disponible (~$21/mes en vez de ~$11/mes) para futuras decisiones de gasto que ya requieren aprobación explícita del usuario de todas formas (regla 8 sin cambios en ese punto).

## Consecuencias

- Positivas: más margen para decisiones futuras (ej. si se necesita un tier superior de algún proveedor, o hosting no-free al acercarse a producción real).
- Negativas: ninguna — no se compromete gasto nuevo con este ADR, solo se actualiza el techo disponible.
- Trigger de revisión: ninguno específico — el presupuesto se revisa cuando el usuario decida cambiarlo, como ahora.

## Fuentes

Confirmación directa del usuario, 2026-09-24, en esta sesión.
