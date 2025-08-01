
#!/usr/bin/env python3
"""
wsgi.py - Punto de entrada WSGI para Easypanel
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno ANTES que todo
load_dotenv()

# Agregar directorio actual al path
sys.path.insert(0, os.path.dirname(__file__))

# Importar y configurar la app
from app import app, initialize_app

# Inicializar aplicación
initialize_app()

# Configuración específica para Easypanel
if __name__ == "__main__":
    # Solo para testing, normalmente Gunicorn maneja esto
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)