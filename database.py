import os
import logging
from datetime import datetime
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import pooling, errorcode

# Cargar .env
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.connection_pool = None
        self.create_connection_pool()

    def create_connection_pool(self):
        try:
            # Opciones de SSL - Intenta verificar el certificado del servidor
            ssl_config = {
                'ssl_disabled': False,
                # 'ssl_verify_cert': True, # Puedes activar esto si tienes problemas de certificado
                # 'ssl_verify_identity': True, # Puedes activar esto si tienes problemas de certificado
                # 'ssl_ca': '/path/to/ca-cert.pem', # Si necesitas un certificado CA específico
            }

            self.connection_pool = pooling.MySQLConnectionPool(
                pool_name="incalake_pool",
                pool_size=5,
                host=os.getenv("DB_HOST"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME"),
                port=int(os.getenv("DB_PORT", 3306)),
                autocommit=True,
                # ssl_disabled=True, # <-- ELIMINA esta línea
                **ssl_config # <-- AÑADE esta línea
            )
            logger.info("✅ Pool de conexiones MySQL creado")
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                logger.error("❌ Error de autenticación con MySQL")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                logger.error("❌ La base de datos no existe")
            else:
                logger.error(f"❌ Error de conexión a MySQL: {err}")
            raise
        except Exception as e:
            logger.error(f"❌ Error inesperado: {str(e)}")
            raise

    def get_connection(self):
        try:
            return self.connection_pool.get_connection()
        except Exception as e:
            logger.error(f"❌ Error obteniendo conexión: {str(e)}")
            raise

    def release_connection(self, connection):
        try:
            connection.close()
        except Exception as e:
            logger.error(f"❌ Error liberando conexión: {str(e)}")

    def verificar_y_migrar_esquema(self):
        """Verifica y migra el esquema existente para agregar columnas faltantes."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Verificar y agregar columna session_id a usuarios_chatbot si no existe
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_schema = %s 
                AND table_name = 'usuarios_chatbot' 
                AND column_name = 'session_id'
            """, (os.getenv("DB_NAME"),))
            
            if cursor.fetchone()[0] == 0:
                logger.info("📝 Agregando columna 'session_id' a usuarios_chatbot...")
                cursor.execute("""
                    ALTER TABLE usuarios_chatbot 
                    ADD COLUMN session_id VARCHAR(255) UNIQUE
                """)
                logger.info("✅ Columna 'session_id' agregada")
            
            # Verificar y agregar columna ultimo_acceso si no existe
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_schema = %s 
                AND table_name = 'usuarios_chatbot' 
                AND column_name = 'ultimo_acceso'
            """, (os.getenv("DB_NAME"),))
            
            if cursor.fetchone()[0] == 0:
                logger.info("📝 Agregando columna 'ultimo_acceso' a usuarios_chatbot...")
                cursor.execute("""
                    ALTER TABLE usuarios_chatbot 
                    ADD COLUMN ultimo_acceso TIMESTAMP NULL
                """)
                logger.info("✅ Columna 'ultimo_acceso' agregada")
            
            # Verificar y agregar columnas faltantes a mensajes_chatbot
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_schema = %s 
                AND table_name = 'mensajes_chatbot' 
                AND column_name = 'session_id'
            """, (os.getenv("DB_NAME"),))
            
            if cursor.fetchone()[0] == 0:
                logger.info("📝 Agregando columna 'session_id' a mensajes_chatbot...")
                cursor.execute("""
                    ALTER TABLE mensajes_chatbot 
                    ADD COLUMN session_id VARCHAR(255) NOT NULL DEFAULT ''
                """)
                logger.info("✅ Columna 'session_id' agregada a mensajes_chatbot")
            
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_schema = %s 
                AND table_name = 'mensajes_chatbot' 
                AND column_name = 'rol'
            """, (os.getenv("DB_NAME"),))
            
            if cursor.fetchone()[0] == 0:
                logger.info("📝 Agregando columna 'rol' a mensajes_chatbot...")
                cursor.execute("""
                    ALTER TABLE mensajes_chatbot 
                    ADD COLUMN rol ENUM('user', 'model') NOT NULL DEFAULT 'user'
                """)
                logger.info("✅ Columna 'rol' agregada a mensajes_chatbot")
            
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_schema = %s 
                AND table_name = 'mensajes_chatbot' 
                AND column_name = 'contenido'
            """, (os.getenv("DB_NAME"),))
            
            if cursor.fetchone()[0] == 0:
                logger.info("📝 Agregando columna 'contenido' a mensajes_chatbot...")
                cursor.execute("""
                    ALTER TABLE mensajes_chatbot 
                    ADD COLUMN contenido TEXT
                """)
                logger.info("✅ Columna 'contenido' agregada a mensajes_chatbot")
                
        except mysql.connector.Error as err:
            logger.error(f"❌ Error en migración de esquema: {err}")
            raise
        finally:
            if conn:
                self.release_connection(conn)

    def create_tables(self):
        """Método principal para verificar y migrar esquema."""
        logger.info("🔍 Verificando esquema de base de datos...")
        self.verificar_y_migrar_esquema()
        logger.info("✅ Esquema verificado y actualizado")

    def verificar_conexion(self):
        """Verifica si la conexión a la base de datos está funcionando."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"❌ Error verificando conexión: {str(e)}")
            return False
        finally:
            if conn:
                self.release_connection(conn)

    def obtener_usuario_por_correo(self, correo):
        """Obtiene un usuario por su correo electrónico."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM usuarios_chatbot WHERE correo = %s", (correo,))
            usuario = cursor.fetchone()
            
            # Mapear campos del esquema actual al esperado
            if usuario:
                usuario['whatsapp'] = usuario.get('telefono', '')  # telefono -> whatsapp
                
            return usuario
        except mysql.connector.Error as err:
            logger.error(f"❌ Error al obtener usuario por correo: {err}")
            return None
        finally:
            if conn:
                self.release_connection(conn)

    def obtener_usuario_por_session(self, session_id):
        """Obtiene un usuario por su session_id."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM usuarios_chatbot WHERE session_id = %s", (session_id,))
            usuario = cursor.fetchone()
            
            if usuario:
                # Mapear campos y actualizar último acceso
                usuario['whatsapp'] = usuario.get('telefono', '')
                
                # Actualizar último acceso si la columna existe
                try:
                    cursor.execute(
                        "UPDATE usuarios_chatbot SET ultimo_acceso = NOW() WHERE id = %s", 
                        (usuario['id'],)
                    )
                except mysql.connector.Error:
                    pass  # Ignorar si la columna ultimo_acceso no existe aún
                
            return usuario
        except mysql.connector.Error as err:
            logger.error(f"❌ Error al obtener usuario por session: {err}")
            return None
        finally:
            if conn:
                self.release_connection(conn)

    def crear_usuario(self, nombre, correo, whatsapp, session_id):
        """Crea un nuevo usuario adaptado al esquema actual."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Usar 'telefono' en lugar de 'whatsapp' para tu esquema
            cursor.execute("""
                INSERT INTO usuarios_chatbot (nombre, correo, telefono, session_id, fecha_registro)
                VALUES (%s, %s, %s, %s, NOW())
            """, (nombre, correo, whatsapp, session_id))
            
            return cursor.lastrowid
        except mysql.connector.Error as err:
            logger.error(f"❌ Error al crear usuario: {err}")
            return None
        finally:
            if conn:
                self.release_connection(conn)

    def actualizar_usuario(self, usuario_id, nombre=None, whatsapp=None, session_id=None):
        """Actualiza los datos de un usuario existente."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if nombre:
                updates.append("nombre = %s")
                params.append(nombre)
            if whatsapp:
                updates.append("telefono = %s")  # telefono en lugar de whatsapp
                params.append(whatsapp)
            if session_id:
                updates.append("session_id = %s")
                params.append(session_id)
            
            if not updates:
                return True
            
            params.append(usuario_id)
            query = f"UPDATE usuarios_chatbot SET {', '.join(updates)}"
            
            # Verificar ultimo_acceso solo si la columna existe
            try:
                cursor.execute("DESCRIBE usuarios_chatbot")
                columnas_info = cursor.fetchall()
                columnas = [row[0] for row in columnas_info]
                if 'ultimo_acceso' in columnas:
                    query += ", ultimo_acceso = NOW()"
            except:
                pass
                
            query += " WHERE id = %s"
            
            cursor.execute(query, params)
            return cursor.rowcount > 0
        except mysql.connector.Error as err:
            logger.error(f"❌ Error al actualizar usuario: {err}")
            return False
        finally:
            if conn:
                self.release_connection(conn)

    def insertar_usuario(self, nombre, correo, whatsapp, session_id):
        """Método de compatibilidad."""
        return self.crear_usuario(nombre, correo, whatsapp, session_id) is not None

    def obtener_historial_chat(self, session_id, limite=None):
        """Obtiene historial adaptado al esquema actual."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()  # NO usar dictionary=True para DESCRIBE
            
            # Verificar qué columnas existen
            cursor.execute("DESCRIBE mensajes_chatbot")
            columnas_info = cursor.fetchall()
            columnas = [row[0] for row in columnas_info]  # Extraer nombres de columnas
            
            # Cambiar a dictionary=True para las consultas reales
            cursor = conn.cursor(dictionary=True)
            
            historial_gemini = []
            
            if 'rol' in columnas and 'contenido' in columnas:
                # Usar esquema nuevo si existe
                query = """
                    SELECT rol, contenido, fecha 
                    FROM mensajes_chatbot 
                    WHERE session_id = %s 
                    ORDER BY fecha ASC
                """
                if limite:
                    query += f" LIMIT {limite}"
                
                cursor.execute(query, (session_id,))
                mensajes = cursor.fetchall()
                
                for msg in mensajes:
                    historial_gemini.append({
                        'role': msg['rol'],
                        'parts': [msg['contenido']]
                    })
            else:
                # Usar esquema original si no se ha migrado
                query = """
                    SELECT mensaje_usuario, respuesta_bot, fecha 
                    FROM mensajes_chatbot 
                    WHERE usuario_id IN (
                        SELECT id FROM usuarios_chatbot WHERE session_id = %s
                    )
                    ORDER BY fecha ASC
                """
                if limite:
                    query += f" LIMIT {limite//2}"  # Dividir por 2 porque cada fila son 2 mensajes
                
                cursor.execute(query, (session_id,))
                mensajes = cursor.fetchall()
                
                for msg in mensajes:
                    if msg['mensaje_usuario']:
                        historial_gemini.append({
                            'role': 'user',
                            'parts': [msg['mensaje_usuario']]
                        })
                    if msg['respuesta_bot']:
                        historial_gemini.append({
                            'role': 'model',
                            'parts': [msg['respuesta_bot']]
                        })
            
            return historial_gemini
        except mysql.connector.Error as err:
            logger.error(f"❌ Error al obtener historial: {err}")
            return []
        finally:
            if conn:
                self.release_connection(conn)

    def guardar_mensaje(self, session_id, usuario_id, rol, contenido):
        """Guarda un mensaje individual (esquema nuevo)."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()  # NO usar dictionary=True para DESCRIBE
            
            # Verificar si existe el esquema nuevo
            cursor.execute("DESCRIBE mensajes_chatbot")
            columnas_info = cursor.fetchall()
            columnas = [row[0] for row in columnas_info]  # Extraer nombres de columnas
            
            if 'rol' in columnas and 'contenido' in columnas:
                cursor.execute("""
                    INSERT INTO mensajes_chatbot (session_id, usuario_id, rol, contenido, fecha)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (session_id, usuario_id, rol, contenido))
                return True
            else:
                logger.warning("⚠️ Esquema antiguo detectado, usa guardar_mensajes_transaccionales")
                return False
                
        except mysql.connector.Error as err:
            logger.error(f"❌ Error al guardar mensaje: {err}")
            return False
        finally:
            if conn:
                self.release_connection(conn)

    def guardar_mensajes_transaccionales(self, session_id, usuario_id, pregunta, respuesta):
        """Guarda pregunta y respuesta adaptado al esquema actual."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()  # NO usar dictionary=True para DESCRIBE
            
            # Verificar esquema disponible
            cursor.execute("DESCRIBE mensajes_chatbot")
            columnas_info = cursor.fetchall()
            columnas = [row[0] for row in columnas_info]  # Extraer nombres de columnas
            
            conn.start_transaction()
            
            if 'rol' in columnas and 'contenido' in columnas:
                # Usar esquema nuevo
                cursor.execute("""
                    INSERT INTO mensajes_chatbot (session_id, usuario_id, rol, contenido, fecha)
                    VALUES (%s, %s, 'user', %s, NOW())
                """, (session_id, usuario_id, pregunta))
                
                cursor.execute("""
                    INSERT INTO mensajes_chatbot (session_id, usuario_id, rol, contenido, fecha)
                    VALUES (%s, %s, 'model', %s, NOW())
                """, (session_id, usuario_id, respuesta))
            else:
                # Usar esquema original
                cursor.execute("""
                    INSERT INTO mensajes_chatbot (usuario_id, mensaje_usuario, respuesta_bot, fecha)
                    VALUES (%s, %s, %s, NOW())
                """, (usuario_id, pregunta, respuesta))
            
            conn.commit()
            return True
        except mysql.connector.Error as err:
            logger.error(f"❌ Error al guardar mensajes (transacción): {err}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self.release_connection(conn)

    def limpiar_historial_sesion(self, session_id):
        """Limpia el historial de mensajes para una sesión."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()  # NO usar dictionary=True para DESCRIBE
            
            # Verificar esquema
            cursor.execute("DESCRIBE mensajes_chatbot")
            columnas_info = cursor.fetchall()
            columnas = [row[0] for row in columnas_info]  # Extraer nombres de columnas
            
            if 'session_id' in columnas:
                cursor.execute("DELETE FROM mensajes_chatbot WHERE session_id = %s", (session_id,))
            else:
                # Esquema original - eliminar por usuario_id
                cursor.execute("""
                    DELETE FROM mensajes_chatbot 
                    WHERE usuario_id IN (
                        SELECT id FROM usuarios_chatbot WHERE session_id = %s
                    )
                """, (session_id,))
            
            return cursor.rowcount > 0
        except mysql.connector.Error as err:
            logger.error(f"❌ Error al limpiar historial: {err}")
            return False
        finally:
            if conn:
                self.release_connection(conn)

# Instancia global
db_manager = DatabaseManager()
