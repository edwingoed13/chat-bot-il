# Multi-stage build para optimizar el tamaño de la imagen
FROM python:3.11-slim as builder

# Instalar dependencias de construcción
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements.txt
COPY requirements.txt .

# Instalar dependencias en un directorio virtual
RUN pip install --upgrade pip
RUN pip install --no-cache-dir --user -r requirements.txt

# Etapa final
FROM python:3.11-slim

# Crear usuario no-root para seguridad
RUN useradd --create-home --shell /bin/bash app

# Instalar solo las dependencias runtime necesarias
RUN apt-get update && apt-get install -y \
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
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# Comando para ejecutar la aplicación
CMD ["python", "app.py"]
