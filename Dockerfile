FROM python:3.10-slim

WORKDIR /app

# Copiar metadatos del paquete e instalar dependencias primero (capa cacheable).
COPY pyproject.toml ./
# Copia opcional de requirements.txt para proyectos que lo usen.
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Instalar el paquete del proyecto en modo editable y pytest para CI.
COPY . .
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir pytest

# El CMD o ENTRYPOINT se definirá en el docker-compose.yml
# dependiendo del rol del contenedor (peer, publicador, frontend).
