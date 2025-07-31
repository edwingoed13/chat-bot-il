# Usar imagen base de Python
FROM python:3.9-slim

# Instalar dependencias del sistema si son necesarias
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements primero (para mejor cache de Docker)
COPY requirements.txt .

# Actualizar pip y instalar dependencias
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Crear directorio para logs si no existe
RUN mkdir -p /app/logs

# Exponer el puerto
EXPOSE 5000

# Verificar que app.py existe
RUN ls -la /app/

# Comando para ejecutar la aplicación
CMD ["python", "app.py"]