# Agentes automatizados de CivicMesh

Tres agentes auxiliares de GitHub Actions, reutilizando el mismo enfoque
usado en el Laboratorio 2. Los tres son **estrictamente auxiliares**:

- **Nunca** aprueban ni fusionan Pull Requests.
- **Nunca** hacen push directo a `main`.
- **Nunca** modifican código silenciosamente (no editan archivos del
  repositorio; solo crean issues o comentan PRs).
- **Nunca** reemplazan al CI ni deciden por sí mismos cambios de protocolo
  o semántica distribuida (Gossip, membership, timeout/fallos, Pub/Sub,
  `should_forward`, TTL, prioridad, modelos estadísticos). Esos casos se
  marcan explícitamente con la leyenda `Requiere intervención humana`.

El merge y la aprobación de cualquier Pull Request son siempre responsabilidad
humana.

## Los tres agentes

### 1. Documentador (`documenter.py`)

Revisa `README.md`, `CHANGELOG.md` y `docs/` en busca de: documentación
inexistente o mínima, referencias/links locales rotos, y paquetes públicos
de `civicmesh/` sin docstring de módulo. Crea issues con las etiquetas
`agent-documenter` y `documentation`.

```bash
python -m scripts.agents.documenter --dry-run   # solo imprime, no crea nada
python -m scripts.agents.documenter             # crea issues reales (requiere gh autenticado)
```

Triggers: `workflow_dispatch` (manual) y `schedule` (diario).

### 2. Revisor de bugs (`bug_reviewer.py`)

Analiza estáticamente (con el módulo `ast`, sin ejecutar nada) el código
bajo `civicmesh/`: `except` sin tipo, uso de `random.*` global en vez de un
`random.Random` inyectado, código sin test asociado bajo `tests/`,
recursos (`open`/sockets) fuera de un `with`, y parámetros de función que
nunca se usan. Crea issues con las etiquetas `agent-bug-reviewer` y `bug`.

```bash
python -m scripts.agents.bug_reviewer --dry-run
python -m scripts.agents.bug_reviewer
```

Triggers: `workflow_dispatch` (manual) y `schedule` (diario).

### 3. Revisor de Pull Requests (`pr_reviewer.py`)

Se dispara vía `workflow_run` cuando termina el workflow de CI (`ci.yml`).
Solo actúa si esa corrida corresponde a una Pull Request y terminó con
`conclusion == "success"` — nunca comenta antes de tener resultado de CI, y
nunca sobre una corrida en rojo. Publica un único comentario por PR y por
commit (deduplicado por SHA) resumiendo el resultado de CI, los archivos
cambiados, y si el diff toca código de protocolo/semántica distribuida. El
comentario siempre aclara que el merge y la aprobación son responsabilidad
humana.

```bash
python -m scripts.agents.pr_reviewer --dry-run --event-path ejemplo_evento.json
```

En producción no requiere invocación manual: lo dispara el workflow
`agent-pr-reviewer.yml` vía `workflow_run`.

## Cambios mecánicos vs. que requieren intervención humana

Los tres agentes usan el mismo criterio (`scripts/agents/common.py:requires_human_intervention`):
si una ruta/finding toca Gossip, membership, Pub/Sub, `should_forward`,
forwarding, TTL, prioridad, replay, seeds o RNG, se marca con la leyenda
exacta `Requiere intervención humana`. Todo lo demás (documentación,
formato, tests, configuración no ligada a protocolo) se trata como
mecánico. La lista es deliberadamente amplia: preferimos marcar de más
"requiere intervención humana" antes que tratar como trivial un cambio que
no lo es.

## Deduplicación y límite de issues

Documentador y Revisor de bugs:

- Cada hallazgo tiene una clave estable (`Finding.key`) que se traduce en
  un marcador embebido en el cuerpo del issue
  (`<!-- civicmesh-agent-marker:<agente>:<key> -->`). Antes de crear un
  issue, se busca ese marcador entre los issues abiertos con la etiqueta
  correspondiente; si ya existe, no se duplica.
- Límite: máximo **5 issues automáticos por agente cada 7 días**
  (`common.MAX_ISSUES_PER_WINDOW` / `common.ISSUE_WINDOW_DAYS`).
- **Fail-closed**: si no se puede consultar el estado real de GitHub (CLI
  `gh` no disponible, timeout, error de la API), el agente **no crea**
  issues nuevos en esa corrida, en vez de asumir que el límite no se
  alcanzó.

El Revisor de PR usa el mismo mecanismo de marcador, pero sobre comentarios
de la PR (uno por SHA), para no comentar dos veces el mismo commit.

## Proveedor de IA (GitHub Models por defecto, con fallback estático)

Documentador y Revisor de bugs usan `common.generate_summary()` para
redactar el cuerpo de cada issue con un modelo real; el Revisor de PR no
llama a ningún proveedor (su comentario es siempre determinista).

El proveedor se configura con tres variables de entorno:

```text
AGENT_API_URL
AGENT_API_KEY
AGENT_MODEL
```

`AIProviderConfig.call()` habla el formato **"chat completions" compatible
con OpenAI** (`{"model", "messages": [...]}` → `choices[0].message.content`),
que es el que hablan GitHub Models, OpenAI, Azure OpenAI, OpenRouter y
equivalentes — apuntar `AGENT_API_URL` a cualquiera de ellos funciona sin
tocar código.

**Por defecto, en `agent-documenter.yml` y `agent-bug-reviewer.yml`, ya
apunta a [GitHub Models](https://github.com/marketplace?type=models)**
usando el `GITHUB_TOKEN` automático de cada corrida — no hace falta crear
ninguna cuenta ni secret para que los agentes usen un modelo real:

```yaml
AGENT_API_URL: ${{ secrets.AGENT_API_URL || 'https://models.github.ai/inference/chat/completions' }}
AGENT_API_KEY: ${{ secrets.AGENT_API_KEY || secrets.GITHUB_TOKEN }}
AGENT_MODEL: ${{ secrets.AGENT_MODEL || 'openai/gpt-4o-mini' }}
```

Si en algún momento se configuran `AGENT_API_URL`/`AGENT_API_KEY`/`AGENT_MODEL`
como **secrets del repositorio** (Settings → Secrets and variables →
Actions), esos secrets tienen prioridad sobre el default de GitHub Models —
así se puede migrar a OpenAI/Azure OpenAI/OpenRouter/etc. sin tocar código,
solo cambiando los tres secrets. Ningún valor real está versionado en este
repositorio.

GitHub Models tiene límites de uso por minuto/día según el plan de la
cuenta/organización (más bajos en cuentas gratuitas); si una llamada falla
por *cualquier* motivo (red, timeout, límite de tasa, JSON inválido,
respuesta incompleta, o simplemente porque no hay proveedor configurado),
el agente usa automáticamente un **fallback determinista de análisis
estático**, dejándolo explícito en la salida con la leyenda:

```text
ANÁLISIS ESTÁTICO (sin modelo de IA disponible)
```

Nunca se afirma que un modelo generativo produjo un resultado que en
realidad vino del fallback estático. El fallback es la red de seguridad,
no el comportamiento esperado en cada corrida.

Catálogo de modelos disponibles y sus límites: revisar
[github.com/marketplace?type=models](https://github.com/marketplace?type=models)
en el momento de usarlo — el catálogo y los límites de GitHub Models pueden
cambiar, y `AGENT_MODEL` acepta cualquier identificador de ese catálogo
(formato `editor/nombre-del-modelo`).

## Permisos de GitHub Actions usados

| Workflow | Permisos | Motivo |
| --- | --- | --- |
| `ci.yml` | `contents: read` | Solo necesita leer el código para testear. |
| `agent-documenter.yml` | `contents: read`, `issues: write`, `models: read` | Lee el repo, crea issues, llama a GitHub Models con el `GITHUB_TOKEN` automático. |
| `agent-bug-reviewer.yml` | `contents: read`, `issues: write`, `models: read` | Lee el repo, crea issues, llama a GitHub Models con el `GITHUB_TOKEN` automático. |
| `agent-pr-reviewer.yml` | `contents: read`, `pull-requests: write`, `actions: read` | Lee el repo, comenta PRs, y lee metadata del `workflow_run` de CI que lo dispara. No usa proveedor de IA, no necesita `models: read`. |

Ninguno de los cuatro tiene permisos de escritura sobre `contents` en
`main`, y ninguno puede aprobar/fusionar Pull Requests (`pull-requests:
write` alcanza para comentar, no para aprobar ni fusionar).

## Tests

`scripts/agents/tests/` cubre la lógica crítica sin necesitar acceso real a
GitHub ni a Internet (usa un `FakeGitHubClient` en memoria y mockea
`urllib.request` para el proveedor de IA): deduplicación, límite y
fail-closed, detección de "requiere intervención humana", parsing de
eventos `workflow_run` y resolución de PR por SHA, fallback estático, y
manejo de errores (HTTP, timeout, JSON inválido, `gh` ausente).

```bash
python -m unittest discover -s scripts/agents/tests -t . -v
```

## Evidencias

El registro de evidencias reales (issues/comentarios efectivamente creados
por estos agentes) se mantiene en
[`docs/agents-evidence.md`](../../docs/agents-evidence.md).
