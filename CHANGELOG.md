# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto todavía no tiene una versión publicada (el tag de cierre del
Laboratorio 3 se creará al terminar el laboratorio, no antes).

## [Unreleased]

### Added

- Workflow de CI (`.github/workflows/ci.yml`): corre en cada Pull Request
  hacia `main` (y opcionalmente en push a `main`), con un job estable
  llamado `tests` pensado para configurarse como status check obligatorio.
  Ejecuta los tests unitarios del proyecto (si ya existen en la rama) y los
  de `scripts/agents/`, con permisos mínimos (`contents: read`).
- `Dockerfile` ligero en Python para unificar el entorno de los roles de CivicMesh.
- `docker-compose.yml` base configurado para levantar una malla de 3 peers, 1 publicador y un frontend en una red interna.
- `Makefile` con comandos estándar para el desarrollador y el CI (`test-unit`, `test-integration`, `up`, `down`).
- Workflow de construcción de imagen base (`.github/workflows/build_base_container.yml`): construye y testea un humo (smoke test) de la imagen docker base.
- Tres agentes automatizados auxiliares (`scripts/agents/`): Documentador,
  Revisor de bugs y Revisor de Pull Requests. Ninguno aprueba ni fusiona
  Pull Requests, ni hace push directo a `main`; los cambios de protocolo o
  semántica distribuida se marcan explícitamente como "Requiere
  intervención humana". Incluyen deduplicación y límite de issues
  automáticos (fail-closed si no se puede verificar el estado en GitHub),
  un fallback determinista de análisis estático cuando no hay un proveedor
  de IA configurado, y su propia suite de tests (sin acceso real a GitHub).
- Workflows de los tres agentes (`agent-documenter.yml`,
  `agent-bug-reviewer.yml`: `workflow_dispatch` + `schedule` diario;
  `agent-pr-reviewer.yml`: `workflow_run` sobre CI, solo tras
  `conclusion == success`).
- `docs/git-flow.md`: flujo de ramas, Pull Requests, CI y rol de los
  agentes en la integración a `main`.
- `docs/agents-evidence.md`: tabla preparada para registrar evidencias
  reales de ejecución de los agentes (sin datos inventados).
- Sección breve en `README.md` sobre CI, flujo Git y existencia de los
  agentes, enlazando a la documentación detallada.

### Changed

- Documentador y Revisor de bugs ahora usan un proveedor de IA real por
  defecto (GitHub Models, vía el `GITHUB_TOKEN` automático de cada corrida,
  sin secrets nuevos que crear), en vez de depender solo del fallback
  estático. `AIProviderConfig.call()` pasó a hablar el formato "chat
  completions" compatible con OpenAI (lo hablan GitHub Models, OpenAI,
  Azure OpenAI, OpenRouter, etc.), para poder migrar de proveedor más
  adelante configurando `AGENT_API_URL`/`AGENT_API_KEY`/`AGENT_MODEL` como
  secrets del repositorio, sin tocar código. El fallback determinista de
  análisis estático se mantiene como red de seguridad ante cualquier falla.

> Nota: esta sección registra únicamente lo que introduce la rama
> `chore/git-ci-agents-bootstrap`. El resto de los componentes de CivicMesh
> (Gossip/Membership, Pub/Sub, datos, analítica) se documenta en sus propias
> ramas/Pull Requests, que deberán agregar aquí sus propias entradas al
> integrarse a `main`.
