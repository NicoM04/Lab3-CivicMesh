# Flujo Git de CivicMesh

Este documento describe cómo se integra código a `main` durante el
Laboratorio 3: ramas, Pull Requests, CI y el rol (limitado) de los agentes
automatizados en ese proceso.

## Rama `main`

`main` es la rama estable. No se hacen commits ni push directos sobre ella:
todo cambio llega mediante Pull Request.

La protección formal de `main` en la configuración de GitHub (status checks
obligatorios, revisiones requeridas, etc.) es una **política del proyecto**;
este documento no debe interpretarse como prueba de que esa protección ya
está activada en el repositorio — eso se configura directamente en GitHub
(Settings → Branches) y queda fuera del alcance de este repositorio de
código. El job de CI se llama deliberadamente `tests` (ver
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) para poder
configurarlo como status check obligatorio cuando corresponda.

## Convención de ramas

| Prefijo | Uso |
| --- | --- |
| `feature/*` | Nueva funcionalidad (p. ej. `feature/gossip-membership`). |
| `fix/*` | Corrección de un bug. |
| `docs/*` | Cambios exclusivamente de documentación. |
| `chore/*` | Infraestructura/tooling del proyecto (CI, agentes, configuración) — como esta misma rama, `chore/git-ci-agents-bootstrap`. |

## Flujo de una Pull Request

1. Se crea una rama con el prefijo correspondiente desde `main` actualizado.
2. Se desarrolla y se commitea en esa rama (commits separados y ordenados
   por concern, no un único commit gigante).
3. Se abre una Pull Request hacia `main`.
4. El workflow de CI (`tests`) corre automáticamente sobre la PR.
5. Con CI en verde, el agente Revisor de Pull Requests
   (`scripts/agents/pr_reviewer.py`) publica un comentario informativo:
   resultado de CI, archivos cambiados, y si el cambio toca código de
   protocolo/semántica distribuida (Gossip, membership, Pub/Sub,
   `should_forward`, TTL, prioridad) — en ese caso, con la leyenda
   `Requiere intervención humana`. Ese comentario **no es una aprobación**.
6. Una persona revisa la PR (código + comentario del agente, si existe) y
   decide si aprobarla.
7. El merge a `main` lo hace una persona, nunca un agente ni un workflow
   automático.

Los agentes documentador y revisor de bugs corren independientemente de las
PRs (manual vía `workflow_dispatch`, o diariamente vía `schedule`) y abren
issues sobre el estado general del repositorio, no comentarios en PRs
puntuales. Ver [`scripts/agents/README.md`](../scripts/agents/README.md)
para el detalle de los tres agentes.

## Qué pueden y qué NO pueden hacer los agentes

Ver el detalle completo en
[`scripts/agents/README.md`](../scripts/agents/README.md). En resumen: solo
pueden crear issues o comentar Pull Requests; nunca aprueban, nunca
fusionan, nunca hacen push directo, nunca modifican código, y nunca deciden
por sí mismos cambios de protocolo o semántica distribuida.

## Issues

Se usan para reportar bugs, tareas pendientes y dependencias entre roles.
Los issues abiertos automáticamente por los agentes llevan las etiquetas
`agent-documenter`/`agent-bug-reviewer` según corresponda, más `documentation`
o `bug`, y quedan sujetos a un límite de 5 por agente cada 7 días (ver
`scripts/agents/common.py`).
