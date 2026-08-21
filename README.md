# Lab3-CivicMesh

## Integración a `main`, CI y agentes automatizados

CivicMesh integra cambios a `main` exclusivamente mediante Pull Requests:
cada PR corre el workflow de CI (job `tests`) y requiere revisión humana
antes de fusionarse. La protección formal de `main` en la configuración de
GitHub (status checks obligatorios, etc.) es una política del proyecto —
este README no afirma que ya esté activada en GitHub, solo que es así como
se trabaja. El detalle completo del flujo de ramas, Pull Requests e issues
está en [docs/git-flow.md](docs/git-flow.md).

El repositorio usa tres agentes auxiliares de GitHub Actions (documentador,
revisor de bugs, revisor de Pull Requests). Son estrictamente auxiliares:
**nunca aprueban ni fusionan Pull Requests, nunca hacen push directo a
`main`, y nunca deciden cambios de protocolo o semántica distribuida**
(Gossip, membership, Pub/Sub, `should_forward`, TTL, prioridad) — esas
decisiones son siempre responsabilidad humana. Su documentación específica
(qué hace cada uno, límites, deduplicación de issues, configuración
opcional de un proveedor de IA) está en
[scripts/agents/README.md](scripts/agents/README.md).
