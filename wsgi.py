#!/usr/bin/env python3
"""
wsgi.py - Punto de entrada WSGI para producción en Easypanel
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
try:
    initialize_app()
    print("✅ Aplicación inicializada correctamente para WSGI")
except Exception as e:
    print(f"❌ Error inicializando aplicación: {e}")
    raise

# Para Gunicorn
application = app

# Para testing local con wsgi
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Ejecutando en modo de desarrollo en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
