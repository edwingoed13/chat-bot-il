# Multi-stage build optimizado para IncaLake Chatbot
FROM python:3.11-slim as builder

# Instalar dependencias de construcción (incluyendo MySQL)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements.txt
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --upgrade pip
RUN pip install --no-cache-dir --user -r requirements.txt

# Etapa final
FROM python:3.11-slim

# Crear usuario no-root para seguridad
RUN useradd --create-home --shell /bin/bash app

# Instalar dependencias runtime necesarias (MySQL client)
RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar las dependencias instaladas desde la etapa builder
COPY --from=builder /root/.local /home/app/.local

# Establecer directorio de trabajo
WORKDIR /app

# Copiar el código de la aplicación
COPY . .

# Cambiar propietario de los archivos al usuario app
RUN chown -R app:app /app

# Cambiar al usuario app
USER app

# Asegurar que el PATH incluya el directorio local de pip
ENV PATH=/home/app/.local/bin:$PATH

# Exponer el puerto
EXPOSE 5000

# Variables de entorno para Flask
ENV FLASK_APP=wsgi.py
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health', timeout=5)" || exit 1

# Comando para ejecutar con Gunicorn (recomendado)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 --access-logfile - --error-logfile - wsgi:app"]

# Alternativa con Flask directo (comentar línea anterior y descomentar esta si hay problemas)
# CMD ["python", "app.py"]
