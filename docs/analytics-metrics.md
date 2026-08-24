# Métricas de Analítica

El Rol 4 utilizará archivos JSONL almacenados en:

$CIVICMESH_RUNS/<run_id>/metrics/

Cada peer podrá registrar periódicamente información necesaria para
calcular las métricas y alimentar el frontend.

## Estado de tópico

Datos mínimos:

- peer_id
- domain
- topic
- channel
- sim_time
- value

Permite calcular:
- convergencia entre peers;
- percepción frente a realidad.

## Estado de red

Datos mínimos:

- peer_id
- sim_time
- known_peers
- alive_peers
- dead_peers

Permite analizar el comportamiento de la red durante caídas o
particiones.

## Propagación de mensajes

Cuando Pub/Sub esté completamente integrado se podrán registrar:

- msg_id
- topic
- channel
- hop_count
- ttl
- priority

Estos datos permitirán analizar la propagación de mensajes y comparar
configuraciones del protocolo.

## Formato

Se utilizará JSONL, con un archivo de métricas por peer cuando sea
posible.

Las métricas globales como convergencia y divergencia serán calculadas
por el módulo de Analítica y no directamente por cada peer.