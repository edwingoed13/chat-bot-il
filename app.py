import os
from dotenv import load_dotenv
import glob

# --- Cargar variables de entorno ANTES de todo ---
load_dotenv()

import json
import time
import re
import logging
import sys
import codecs
from datetime import datetime
from email_validator import validate_email, EmailNotValidError
import google.generativeai as genai
from flask import Flask, request, Response, jsonify
from flask_cors import CORS

# Debug opcional para ver la carga de variables
print("DEBUG DB_PASSWORD:", os.getenv("DB_PASSWORD"))

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# --- Configuración de logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # ya con UTF-8
        logging.FileHandler('app.log', encoding='utf-8')  # importante para el archivo también
    ]
)
logger = logging.getLogger(__name__)

# --- Validación de variables de entorno ---
required_env_vars = [
    'GEMINI_API_KEY',
    'DB_HOST',
    'DB_NAME',
    'DB_USER',
    'DB_PASSWORD'
]

for var in required_env_vars:
    if os.getenv(var) is None:
        logger.error(f"❌ Variable de entorno requerida faltante: {var}")
        raise ValueError(f"La variable {var} no está configurada.")

# --- Inicializar Flask y DB ---
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Importar después de cargar entorno y validar
from database import db_manager
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

gemini_model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-exp",  # Cambiado a Gemini 2.0 Flash Experimental
    generation_config={
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 8192,
    },
    safety_settings=[
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]
)

# --- Constantes y configuraciones ---
MAX_HISTORY_TURNS = 5
MAX_SESSION_AGE_DAYS = 30

# === Funciones de utilidad ===
def validate_user_data(nombre, correo, whatsapp):
    """Valida los datos del usuario."""
    if not nombre or len(nombre.strip()) < 2:
        return False, "El nombre debe tener al menos 2 caracteres"
    
    try:
        valid = validate_email(correo)
        correo = valid.email  # forma normalizada
    except EmailNotValidError as e:
        return False, f"Correo electrónico inválido: {str(e)}"
    
    if not whatsapp or not whatsapp.strip().isdigit() or len(whatsapp) < 6:
        return False, "Número de WhatsApp inválido (debe contener solo números y tener al menos 6 dígitos)"
    
    return True, ""

def cargar_tours():
    """Carga la información de tours desde el archivo JSON."""
    try:
        with open('tours_ingles.json', 'r', encoding='utf-8') as f:
            tours_data = json.load(f)
        logger.info(f"✅ {len(tours_data)} tours cargados desde tours_ingles.json")
        return tours_data
    except FileNotFoundError:
        logger.error("❌ Error: tours_ingles.json no encontrado")
        return []
    except json.JSONDecodeError:
        logger.error("❌ Error al decodificar tours_ingles.json")
        return []

tours_data_loaded = cargar_tours()
# === Configuraciones por idioma actualizadas ===
LANGUAGE_CONFIGS = {
    'es': {
        'stopwords': {'de', 'a', 'el', 'la', 'los', 'las', 'un', 'una', 'y', 'o', 'pero', 'con', 'para', 'qué', 'quiero', 'tienes', 'hay', 'es'},
        'system_instruction': (
            "Eres un asistente de viajes especializado de IncaLake, una agencia peruana experta en Puno y Lago Titicaca. 🏔️ Utiliza emojis para hacer la conversación más amena.\n\n"
            "🎯 ESPECIALIZACIÓN DE INCALAKE:\n"
            "1. DESTINO PRINCIPAL: Puno y Lago Titicaca (nuestra especialidad) 🌊\n"
            "2. Destinos secundarios: Bolivia, Arequipa, Cusco\n"
            "3. Siempre prioriza tours con 'prioridad' más baja (1 = máxima prioridad, 5 = mínima)\n"
            "4. Para experiencias auténticas, sugiere homestays o tours de 2d1n\n\n"
            "📝 FLUJO DE CONVERSACIÓN:\n"
            "- Los datos de contacto ya fueron recolectados previamente ✅\n"
            "- Para consultas GENERALES, pregunta: '¿Para qué fecha planeas viajar y cuántas personas van?' 🗓️👥\n"
            "- Para consultas ESPECÍFICAS, usa 'Relevant Tour Information' y luego consulta fecha/personas si es necesario\n"
            "- SIEMPRE recomienda Puno/Titicaca como primera opción cuando sea relevante\n\n"
            "🌊 INFORMACIÓN CLAVE DE PUNO:\n"
            "- Lago Titicaca: 3,812 msnm - Recomendamos 1 día de aclimatación en Puno\n"
            "- Menciona nuestras islas especializadas: Uros, Taquile, Amantani\n"
            "- Destaca experiencias únicas como homestays con familias locales\n\n"
            "💰 PRESENTACIÓN DE TOURS:\n"
            "- SIEMPRE incluye URL clickeable: [Ver más información](URL_COMPLETA)\n"
            "- Consulta 'Prices (per person)' para rangos exactos\n"
            "- Máximo 3 párrafos, sé conciso y directo\n"
            "- Formato: título, descripción breve, precios, URL clickeable\n\n"
            "🚀 PROCESO DE RESERVA:\n"
            "Para reservar, comparte la URL clickeable e indica:\n"
            "1️⃣ Seleccionar fecha del tour\n"
            "2️⃣ Elegir hora de inicio\n"
            "3️⃣ Indicar número de personas\n"
            "4️⃣ Presionar 'Comprar' y completar pago\n"
            "⚠️ Si hay algún percance o la opción 'Comprar' no funciona, contactar WhatsApp +51982769453\n\n"
            "❓ CONSULTAS ESPECIALES:\n"
            "Para reservas existentes, documentos sensibles o consultas complejas:\n"
            "'Para este tipo de consulta tan específica, uno de mis compañeros humanos te ayudará. En breve se pondrán en contacto contigo. Si prefieres, puedes escribirnos directamente a nuestro WhatsApp +51982769453 para una atención inmediata.' 📞\n\n"
            "🌐 Para recomendaciones generales, usa información del blog incalake.com/blog\n"
            "⚠️ NUNCA redirijas a otras agencias de viajes"
        ),
        'greeting': "¡Hola! 👋 Soy tu asistente especializado de IncaLake. ¿En qué aventura por Puno y el Lago Titicaca te puedo ayudar hoy? 🌊✨",
        'error_message': "Lo siento, ocurrió un error en el servidor. Por favor, intenta más tarde o contáctanos al +51982769453 😔",
        'no_tours_message': "No encontré información específica para esa consulta, pero puedo ayudarte con nuestros tours en Puno y Lago Titicaca 🌊",
        'general_response_template': (
            "¡Perfecto! 🎉 Como especialistas en Puno y Lago Titicaca, tenemos las mejores experiencias:\n\n"
            "🌊 **PUNO - LAGO TITICACA** (Nuestra especialidad):\n"
            "• Islas Flotantes de los Uros - Experiencia única en totora 🛶\n"
            "• Isla Taquile - Cultura viva y textilería ancestral 🧵\n"
            "• Isla Amantani - Homestays auténticos con familias locales 🏠\n"
            "• Tours de 2d1n para experiencias completas\n"
            "*Altitud: 3,812 msnm - Recomendamos 1 día de aclimatación*\n\n"
            "🌟 **Otros destinos disponibles**:\n"
            "🧂 Bolivia: Salar de Uyuni | 🌋 Arequipa: Cañón del Colca | 🏛️ Cusco: Machu Picchu\n\n"
            "Para recomendarte la experiencia perfecta: **¿Para qué fecha planeas viajar y cuántas personas van?** 📅👥"
        ),
        'puno_priority_message': "🌊 Como especialistas en Puno y Lago Titicaca, te recomiendo especialmente nuestros tours a las islas. ¿Te interesan las experiencias en Uros, Taquile o Amantani?"
    },
    'en': {
        'stopwords': {'the', 'a', 'an', 'and', 'or', 'but', 'with', 'for', 'what', 'want', 'have', 'is', 'are', 'to', 'of', 'in', 'on', 'at'},
        'system_instruction': (
            "You are a specialized travel assistant for IncaLake, a Peruvian agency expert in Puno and Lake Titicaca. 🏔️ Use emojis to make conversations more enjoyable.\n\n"
            "🎯 INCALAKE SPECIALIZATION:\n"
            "1. MAIN DESTINATION: Puno and Lake Titicaca (our specialty) 🌊\n"
            "2. Secondary destinations: Bolivia, Arequipa, Cusco\n"
            "3. Always prioritize tours with lower 'priority' numbers (1 = highest priority, 5 = lowest)\n"
            "4. For authentic experiences, suggest homestays or 2d1n tours\n\n"
            "📝 CONVERSATION FLOW:\n"
            "- Contact information was already collected previously ✅\n"
            "- For GENERAL queries, ask: 'What date are you planning to travel and how many people are going?' 🗓️👥\n"
            "- For SPECIFIC queries, use 'Relevant Tour Information' then ask for date/people if needed\n"
            "- ALWAYS recommend Puno/Titicaca as first option when relevant\n\n"
            "🌊 KEY PUNO INFORMATION:\n"
            "- Lake Titicaca: 3,812 masl - We recommend 1 day acclimatization in Puno\n"
            "- Mention our specialized islands: Uros, Taquile, Amantani\n"
            "- Highlight unique experiences like homestays with local families\n\n"
            "💰 TOUR PRESENTATION:\n"
            "- ALWAYS include clickable URL: [More information](COMPLETE_URL)\n"
            "- Check 'Prices (per person)' for exact ranges\n"
            "- Maximum 3 paragraphs, be concise and direct\n"
            "- Format: title, brief description, prices, clickable URL\n\n"
            "🚀 BOOKING PROCESS:\n"
            "To book, share clickable URL and indicate:\n"
            "1️⃣ Select tour date\n"
            "2️⃣ Choose start time\n"
            "3️⃣ Indicate number of people\n"
            "4️⃣ Press 'Buy' and complete payment\n"
            "⚠️ If there's any issue or 'Buy' option doesn't work, contact WhatsApp +51982769453\n\n"
            "❓ SPECIAL QUERIES:\n"
            "For existing bookings, sensitive documents or complex queries:\n"
            "'For this specific type of query, one of my human colleagues will help you. They will contact you shortly. If you prefer, you can write directly to our WhatsApp +51982769453 for immediate assistance.' 📞\n\n"
            "🌐 For general recommendations, use information from incalake.com/blog\n"
            "⚠️ NEVER redirect to other travel agencies"
        ),
        'greeting': "Hello! 👋 I'm your specialized IncaLake assistant. What Puno and Lake Titicaca adventure can I help you with today? 🌊✨",
        'error_message': "Sorry, a server error occurred. Please try again later or contact us at +51982769453 😔",
        'no_tours_message': "I couldn't find specific information for that query, but I can help you with our Puno and Lake Titicaca tours 🌊",
        'general_response_template': (
            "Perfect! 🎉 As specialists in Puno and Lake Titicaca, we have the best experiences:\n\n"
            "🌊 **PUNO - LAKE TITICACA** (Our specialty):\n"
            "• Floating Islands of Uros - Unique totora reed experience 🛶\n"
            "• Taquile Island - Living culture and ancestral textiles 🧵\n"
            "• Amantani Island - Authentic homestays with local families 🏠\n"
            "• 2d1n tours for complete experiences\n"
            "*Altitude: 3,812 masl - We recommend 1 day acclimatization*\n\n"
            "🌟 **Other available destinations**:\n"
            "🧂 Bolivia: Uyuni Salt Flats | 🌋 Arequipa: Colca Canyon | 🏛️ Cusco: Machu Picchu\n\n"
            "To recommend the perfect experience: **What date are you planning to travel and how many people are going?** 📅👥"
        ),
        'puno_priority_message': "🌊 As specialists in Puno and Lake Titicaca, I especially recommend our island tours. Are you interested in experiences at Uros, Taquile or Amantani?"
    }
}

# === Nuevas funciones para detección de intención ===
def detectar_intencion_consulta(pregunta, language='es'):
    """Detecta intención priorizando Puno/Titicaca como especialidad."""
    pregunta_lower = pregunta.lower()
    
    # Detectar mención de Puno/Titicaca (alta prioridad)
    puno_keywords = ['puno', 'titicaca', 'uros', 'taquile', 'amantani', 'floating islands', 'islas flotantes']
    menciona_puno = any(keyword in pregunta_lower for keyword in puno_keywords)
    
    # Patrones para preguntas muy generales
    patrones_generales = {
        'es': [
            r'\b(info|información)\s+(sobre\s+)?tours?\b',
            r'\btours?\s+(disponibles?|que\s+tienen?)\b',
            r'\bqué\s+tours?\s+(hay|tienen|ofrecen)\b',
            r'\bque\s+actividades?\s+(hay|tienen|ofrecen)\b',
            r'\bque\s+hacer\s+en\s+(perú|peru)\b',
            r'\bturismo\s+en\s+(perú|peru)\b',
            r'^(hola|hello|buenos?\s+días?|buenas?\s+tardes?)',
            r'\bpaquetes?\s+turísticos?\b',
            r'\brecomendaciones?\b'
        ],
        'en': [
            r'\binfo\s+(about\s+)?tours?\b',
            r'\btours?\s+(available|you\s+have)\b',
            r'\bwhat\s+tours?\s+(do\s+you\s+have|are\s+available)\b',
            r'\bwhat\s+activities?\s+(do\s+you\s+have|are\s+available)\b',
            r'\bwhat\s+to\s+do\s+in\s+peru\b',
            r'\btourism\s+in\s+peru\b',
            r'^(hi|hello|good\s+morning|good\s+afternoon)',
            r'\btravel\s+packages?\b',
            r'\brecommendations?\b'
        ]
    }
    
    if menciona_puno:
        return 'specific_puno'
    
    for patron in patrones_generales.get(language, patrones_generales['es']):
        if re.search(patron, pregunta_lower):
            return 'general'
    
    return 'specific'

def obtener_destinos_disponibles():
    """Extrae los destinos únicos de los tours disponibles."""
    destinos = set()
    for tour in tours_data_loaded:
        titulo = tour.get("titulo_producto", "").lower()
        tipo = tour.get("tipo_servicio", "").lower()
        
        if any(word in titulo + " " + tipo for word in ['puno', 'titicaca', 'uros', 'taquile', 'amantani']):
            destinos.add('Puno')
        if any(word in titulo + " " + tipo for word in ['cusco', 'machu picchu', 'sacred valley']):
            destinos.add('Cusco')
        if any(word in titulo + " " + tipo for word in ['arequipa', 'colca', 'canyon']):
            destinos.add('Arequipa')
        if any(word in titulo + " " + tipo for word in ['uyuni', 'salar', 'bolivia']):
            destinos.add('Uyuni')
    
    return sorted(list(destinos))

def contar_tours_por_destino(destino):
    """Cuenta cuántos tours hay para un destino específico."""
    count = 0
    destino_lower = destino.lower()
    
    for tour in tours_data_loaded:
        titulo = tour.get("titulo_producto", "").lower()
        tipo = tour.get("tipo_servicio", "").lower()
        
        if destino_lower == 'puno' and any(word in titulo + " " + tipo for word in ['puno', 'titicaca', 'uros', 'taquile', 'amantani']):
            count += 1
        elif destino_lower == 'cusco' and any(word in titulo + " " + tipo for word in ['cusco', 'machu picchu', 'sacred valley']):
            count += 1
        elif destino_lower == 'arequipa' and any(word in titulo + " " + tipo for word in ['arequipa', 'colca', 'canyon']):
            count += 1
        elif destino_lower == 'uyuni' and any(word in titulo + " " + tipo for word in ['uyuni', 'salar', 'bolivia']):
            count += 1
    
    return count
# === Funciones de Búsqueda y Traducción Contextual ===
def obtener_keywords_contextuales(historial, pregunta_actual, language='es'):
    """Extrae palabras clave del contexto de la conversación según el idioma."""
    texto_a_procesar = pregunta_actual.lower()
    if historial:
        user_messages = [h['parts'][0] for h in historial if h['role'] == 'user']
        texto_a_procesar = " ".join(user_messages[-2:]) + " " + texto_a_procesar

    stopwords = LANGUAGE_CONFIGS[language]['stopwords']
    palabras = re.findall(r'\b\w{3,}\b', texto_a_procesar)
    keywords = {palabra for palabra in palabras if palabra not in stopwords}
    print(f"🔑 Keywords contextuales ({language.upper()}): {keywords}")
    return list(keywords)

def traducir_keywords_a_ingles(keywords, source_language='es'):
    """Usa Gemini para traducir keywords al inglés si es necesario."""
    if not keywords: 
        return []
    
    if source_language == 'en':
        print(f"🌐 Keywords ya en inglés: {keywords}")
        return keywords
    
    prompt = f"Translate the following Spanish travel keywords to English. Provide only the most relevant, single-word English equivalent for each. Return as a comma-separated list. Keywords: '{', '.join(keywords)}'"
    try:
        response = genai.GenerativeModel('gemini-1.5-flash').generate_content(prompt)
        english_keywords = [kw.strip() for kw in response.text.strip().lower().split(',')]
        print(f"🌐 Keywords traducidas (EN): {english_keywords}")
        return english_keywords
    except Exception as e:
        print(f"❌ Error en la traducción de keywords: {e}")
        return keywords

def buscar_tours_relevantes(keywords_en, intencion='specific'):
    """Busca tours priorizando Puno/Titicaca según la especialización."""
    if not keywords_en: 
        return []
    
    scored_tours = []
    for tour in tours_data_loaded:
        score = 0
        texto_busqueda = (
            tour.get("titulo_producto", "") + " " + 
            tour.get("tipo_servicio", "") + " " + 
            tour.get("descripcion_tab", "")
        ).lower()
        
        puno_bonus = 0
        if any(keyword in texto_busqueda for keyword in ['puno', 'titicaca', 'uros', 'taquile', 'amantani']):
            puno_bonus = 10 
        
        for keyword in keywords_en:
            if keyword in texto_busqueda:
                score += 5 if keyword in tour.get("titulo_producto", "").lower() else 1
        
        if score > 0 or puno_bonus > 0:
            score += puno_bonus
            score += (6 - tour.get("prioridad", 5))
            scored_tours.append((score, tour))
    
    scored_tours.sort(key=lambda x: x[0], reverse=True)
    
    if intencion == 'specific_puno':
        puno_tours = [tour for score, tour in scored_tours if score >= 10] 
        return puno_tours[:3] if puno_tours else [tour for score, tour in scored_tours[:2]]
    
    return [tour for score, tour in scored_tours[:3]]

def formatear_contexto_detallado(tours, language='es'):
    """Formatea tours con URLs clickeables y prioridad visible."""
    if not tours: 
        return LANGUAGE_CONFIGS[language]['no_tours_message']
    
    resumen_partes = ["--- Relevant Tour Information ---"]
    for tour in tours:
        titulo = tour.get("titulo_producto", "No title")
        descripcion = tour.get("descripcion_tab", "No description")
        itinerario = tour.get("itinerario_ta", "No itinerary provided.")
        url = tour.get("url_servicio", "")
        prioridad = tour.get("prioridad", 5)
        
        precios_formateados = "Price on request."
        try:
            precios = json.loads(tour.get("precios_rango", "{}"))
            if precios and all(k in precios for k in ["desde", "hasta", "precio"]):
                price_entries = [
                    f"For {d}-{h} people: ${p} USD" 
                    for d, h, p in zip(precios["desde"], precios["hasta"], precios["precio"])
                ]
                precios_formateados = " | ".join(price_entries)
        except (json.JSONDecodeError, TypeError):
            pass
        
        es_puno = any(keyword in titulo.lower() + descripcion.lower() for keyword in ['puno', 'titicaca', 'uros', 'taquile', 'amantani'])
        especialidad_nota = " ⭐ (NUESTRA ESPECIALIDAD)" if es_puno else ""
        
        resumen_partes.append(
            f"\n🎯 Tour: {titulo}{especialidad_nota}\n"
            f"Priority: {prioridad}/5 (1=highest priority)\n"
            f"Description: {descripcion}\n"
            f"Brief Itinerary: {itinerario[:150]}{'...' if len(itinerario) > 150 else ''}\n"
            f"Prices per person: {precios_formateados}\n"
            f"Booking URL: {url}\n"
            f"IMPORTANT: Make URL clickable as: [Ver más información]({url}) (Spanish) or [More information]({url}) (English)"
        )
    
    return "\n".join(resumen_partes)

def construir_historial_gemini(historial_previo, instruccion_principal, contexto_detallado, pregunta_actual, language='es', intencion='specific'):
    """Construye historial optimizado para especialización en Puno."""
    historial_para_gemini = []
    
    historial_para_gemini.append({
        "role": "user", 
        "parts": [instruccion_principal]
    })
    
    es_primera_interaccion = len(historial_previo) == 0
    
    if es_primera_interaccion:
        historial_para_gemini.append({
            "role": "model", 
            "parts": [LANGUAGE_CONFIGS[language]['greeting']]
        })
    else:
        # AQUÍ ESTABA EL PROBLEMA - Esta línea siempre devolvía español
        # ANTES: historial_para_gemini.append({
        #     "role": "model", 
        #     "parts": ["¡Hola de nuevo! ¿En qué más te puedo ayudar? 😊" if language == 'es' else "Hello again! How else can I help you? 😊"]
        # })
        
        # CORREGIDO: Usar la configuración de idioma apropiada
        continuing_message = {
            'es': "¡Hola de nuevo! ¿En qué más te puedo ayudar? 😊",
            'en': "Hello again! How else can I help you? 😊"
        }
        historial_para_gemini.append({
            "role": "model", 
            "parts": [continuing_message.get(language, continuing_message['es'])]
        })
    
    historial_para_gemini.extend(historial_previo)
    
    if intencion == 'general' and es_primera_interaccion:
        destinos = obtener_destinos_disponibles()
        # TAMBIÉN CORREGIR AQUÍ - Usar configuración de idioma
        prompt_template = {
            'es': "CONSULTA GENERAL - PRIMERA INTERACCIÓN. Especialidad: Puno/Titicaca. Otros destinos: {destinos}. Necesita consultar fecha y número de personas.\n\nUser Question: {pregunta}",
            'en': "GENERAL QUERY - FIRST INTERACTION. Specialty: Puno/Titicaca. Other destinations: {destinos}. Need to ask for date and number of people.\n\nUser Question: {pregunta}"
        }
        prompt_actual = prompt_template.get(language, prompt_template['es']).format(
            destinos=', '.join(destinos), 
            pregunta=pregunta_actual
        )
        
    elif intencion == 'specific_puno':
        prompt_template = {
            'es': "CONSULTA ESPECÍFICA SOBRE PUNO/TITICACA (nuestra especialidad) 🌊:\n{contexto}\n\nRecuerda mencionar nuestra experiencia especializada en esta región.\n\nUser Question: {pregunta}",
            'en': "SPECIFIC QUERY ABOUT PUNO/TITICACA (our specialty) 🌊:\n{contexto}\n\nRemember to mention our specialized experience in this region.\n\nUser Question: {pregunta}"
        }
        prompt_actual = prompt_template.get(language, prompt_template['es']).format(
            contexto=contexto_detallado,
            pregunta=pregunta_actual
        )
        
    elif intencion == 'specific':
        prompt_template = {
            'es': "{contexto}\n\nSi es relevante, menciona también nuestros tours especialidad en Puno/Titicaca.\n\nUser Question: {pregunta}",
            'en': "{contexto}\n\nIf relevant, also mention our specialty tours in Puno/Titicaca.\n\nUser Question: {pregunta}"
        }
        prompt_actual = prompt_template.get(language, prompt_template['es']).format(
            contexto=contexto_detallado,
            pregunta=pregunta_actual
        )
    else:
        prompt_template = {
            'es': "Consulta general. Recuerda que somos especialistas en Puno/Titicaca. Necesita fecha y número de personas.\n\nUser Question: {pregunta}",
            'en': "General query. Remember we are specialists in Puno/Titicaca. Need date and number of people.\n\nUser Question: {pregunta}"
        }
        prompt_actual = prompt_template.get(language, prompt_template['es']).format(
            pregunta=pregunta_actual
        )
    
    historial_para_gemini.append({
        "role": "user", 
        "parts": [prompt_actual]
    })
    
    return historial_para_gemini

# === Ruta Principal del Chat ===
# === Endpoints de la API ===
@app.route('/register_user', methods=['POST'])
def register_user():
    """
    Registra un nuevo usuario o actualiza uno existente.
    
    Parámetros (JSON):
    - nombre: Nombre completo del usuario
    - correo: Correo electrónico válido
    - whatsapp: Número de WhatsApp (solo dígitos)
    - session_id: (Opcional) ID de sesión existente
    
    Returns:
    - 200: Usuario registrado/actualizado correctamente
    - 400: Datos inválidos o faltantes
    - 500: Error interno del servidor
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No se proporcionaron datos"}), 400
        
        nombre = data.get('nombre', '').strip()
        correo = data.get('correo', '').strip().lower()
        whatsapp = data.get('whatsapp', '').strip()
        session_id = data.get('session_id', f"session_{int(time.time())}")
        
        # Validar datos
        is_valid, error_msg = validate_user_data(nombre, correo, whatsapp)
        if not is_valid:
            logger.warning(f"Validación fallida: {error_msg}")
            return jsonify({"error": error_msg}), 400
        
        # Verificar si el usuario ya existe
        usuario_existente = db_manager.obtener_usuario_por_correo(correo)
        
        if usuario_existente:
            # Actualizar datos existentes
            logger.info(f"Actualizando usuario existente: {correo}")
            if db_manager.actualizar_usuario(
                usuario_existente['id'],
                nombre=nombre,
                whatsapp=whatsapp,
                session_id=session_id
            ):
                return jsonify({
                    "success": True,
                    "message": "Datos de usuario actualizados",
                    "usuario_id": usuario_existente['id'],
                    "session_id": session_id
                })
            else:
                logger.error("Error al actualizar usuario en la BD")
                return jsonify({"error": "Error al actualizar usuario"}), 500
        
        # Crear nuevo usuario
        logger.info(f"Creando nuevo usuario: {correo}")
        usuario_id = db_manager.crear_usuario(
            nombre=nombre,
            correo=correo,
            whatsapp=whatsapp,
            session_id=session_id
        )
        
        if usuario_id:
            return jsonify({
                "success": True,
                "message": "Usuario registrado exitosamente",
                "usuario_id": usuario_id,
                "session_id": session_id
            })
        else:
            logger.error("Error al crear usuario en la BD")
            return jsonify({"error": "Error al registrar usuario"}), 500
            
    except Exception as e:
        logger.error(f"Error en register_user: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/chat', methods=['POST'])
def chat():
    """
    Procesa mensajes del chat y devuelve respuestas del asistente.
    
    Parámetros (JSON):
    - message: Texto del mensaje del usuario
    - session_id: ID de sesión existente
    - language: (Opcional) Idioma de la conversación (es/en)
    
    Returns:
    - Streaming de la respuesta del asistente
    - 400: Mensaje vacío o datos inválidos
    - 500: Error interno del servidor
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No se proporcionaron datos"}), 400
            
        pregunta = data.get('message', '').strip()
        session_id = data.get('session_id', 'default_session')
        language = data.get('language', 'es')
        
        if language not in LANGUAGE_CONFIGS:
            language = 'es'
            
        logger.info(f"Nueva petición - Sesión: {session_id}, Idioma: {language}")
        
        if not pregunta:
            return jsonify({"error": "El mensaje no puede estar vacío"}), 400

        # Verificar y obtener usuario
        usuario = db_manager.obtener_usuario_por_session(session_id)
        if not usuario:
            logger.warning(f"Sesión no registrada: {session_id}")
            return jsonify({"error": "Por favor regístrate primero"}), 401

        # Cargar historial desde base de datos
        historial = db_manager.obtener_historial_chat(session_id, MAX_HISTORY_TURNS * 2)
        logger.info(f"Historial cargado: {len(historial)} mensajes")
        
        # Procesar intención y contexto
        intencion = detectar_intencion_consulta(pregunta, language)
        logger.info(f"Intención detectada: {intencion}")
        
        contexto_detallado = ""
        if intencion != 'general':
            keywords = obtener_keywords_contextuales(historial, pregunta, language)
            keywords_en = traducir_keywords_a_ingles(keywords, language)
            tours_relevantes = buscar_tours_relevantes(keywords_en)
            contexto_detallado = formatear_contexto_detallado(tours_relevantes, language)

        config = LANGUAGE_CONFIGS[language]
        historial_para_gemini = construir_historial_gemini(
            historial, config['system_instruction'], contexto_detallado, pregunta, language, intencion
        )

        def stream_response():
            nonlocal historial
            respuesta_completa = ""
            
            try:
                # Generar respuesta con Gemini
                response_stream = gemini_model.generate_content(
                    historial_para_gemini, stream=True
                )
                
                for chunk in response_stream:
                    if chunk.text:
                        respuesta_completa += chunk.text
                        yield chunk.text
                        time.sleep(0.01)
                
                # Guardar en base de datos (transaccional)
                if not db_manager.guardar_mensajes_transaccionales(
                    session_id=session_id,
                    usuario_id=usuario['id'],
                    pregunta=pregunta,
                    respuesta=respuesta_completa
                ):
                    logger.error("Error al guardar mensajes en BD")
                
                logger.info(f"Mensajes guardados para sesión: {session_id}")

            except Exception as e:
                logger.error(f"Error en Gemini: {str(e)}", exc_info=True)
                yield config['error_message']

        return Response(stream_response(), mimetype='text/event-stream')
    
    except Exception as e:
        logger.error(f"Error en endpoint /chat: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/session/<session_id>/history', methods=['GET'])
def get_session_history(session_id):
    """
    Obtiene el historial de chat para una sesión específica.
    
    Parámetros:
    - session_id: ID de la sesión
    
    Returns:
    - 200: Historial de mensajes
    - 404: Sesión no encontrada
    - 500: Error interno
    """
    try:
        # Verificar si la sesión existe
        usuario = db_manager.obtener_usuario_por_session(session_id)
        if not usuario:
            return jsonify({"error": "Sesión no encontrada"}), 404
        
        historial = db_manager.obtener_historial_chat(session_id)
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "usuario_id": usuario['id'],
            "historial": historial,
            "count": len(historial)
        })
    except Exception as e:
        logger.error(f"Error obteniendo historial: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/session/<session_id>/clear', methods=['POST'])
def clear_session(session_id):
    """
    Limpia el historial de chat para una sesión específica.
    
    Parámetros:
    - session_id: ID de la sesión
    
    Returns:
    - 200: Historial limpiado
    - 404: Sesión no encontrada
    - 500: Error interno
    """
    try:
        if not db_manager.limpiar_historial_sesion(session_id):
            return jsonify({"error": "Sesión no encontrada"}), 404
        
        return jsonify({
            "success": True,
            "message": f"Historial de sesión {session_id} limpiado"
        })
    except Exception as e:
        logger.error(f"Error limpiando sesión: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/destinations', methods=['GET'])
def get_destinations():
    """
    Obtiene la lista de destinos disponibles con conteo de tours.
    
    Returns:
    - 200: Lista de destinos
    - 500: Error interno
    """
    try:
        destinos = obtener_destinos_disponibles()
        destinos_con_conteo = [
            {"destination": destino, "tour_count": contar_tours_por_destino(destino)}
            for destino in destinos
        ]
        
        return jsonify({
            "success": True,
            "destinations": destinos_con_conteo,
            "total": len(destinos)
        })
    except Exception as e:
        logger.error(f"Error obteniendo destinos: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """
    Endpoint de health check para monitoreo.
    
    Returns:
    - 200: Estado de salud de la aplicación
    - 503: Servicio no disponible
    """
    try:
        # Verificar conexión a la base de datos
        db_status = db_manager.verificar_conexion()
        
        # Verificar tours cargados
        tours_loaded = len(tours_data_loaded) > 0
        
        # Verificar API de Gemini
        gemini_status = False
        try:
            genai.get_model('models/gemini-1.5-pro-latest')
            gemini_status = True
        except Exception:
            pass
        
        status = {
            "status": "healthy" if all([db_status, tours_loaded, gemini_status]) else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "database": db_status,
            "tours_loaded": tours_loaded,
            "gemini_api": gemini_status,
            "version": "3.1.0"
        }
        
        status_code = 200 if status["status"] == "healthy" else 503
        return jsonify(status), status_code
        
    except Exception as e:
        logger.error(f"Error en health check: {str(e)}", exc_info=True)
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503

# === Manejo de errores ===
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint no encontrado"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Método no permitido"}), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Error interno del servidor"}), 500

# === Inicialización ===
def initialize_app():
    """Inicializa la aplicación y verifica dependencias."""
    logger.info("🚀 Iniciando IncaLake Chatbot API")
    
    # Verificar tours cargados
    if not tours_data_loaded:
        logger.warning("⚠️ No se cargaron tours desde tours_ingles.json")
    
    # Verificar conexión a la base de datos
    try:
        db_manager.create_tables()
        logger.info("✅ Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"❌ Error inicializando base de datos: {str(e)}", exc_info=True)
        raise
    
    # Verificar API de Gemini
    try:
        genai.GenerativeModel('gemini-1.5-pro-latest')
        logger.info("✅ Conexión con Gemini API verificada")
    except Exception as e:
        logger.error(f"❌ Error verificando Gemini API: {str(e)}", exc_info=True)
        raise
    
    logger.info("✅ Inicialización completada")

@app.route('/', methods=['GET'])
def root():
    """Endpoint raíz para verificar que la API está funcionando."""
    return jsonify({
        "message": "IncaLake Chatbot API is running",
        "version": "3.1.0",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": [
            "/health",
            "/register_user", 
            "/chat",
            "/destinations",
            "/session/<session_id>/history",
            "/session/<session_id>/clear",
            "/admin/conversations",
            "/admin/conversation/<session_id>/full", 
            "/admin/conversations/search",
            "/admin/stats"
        ]
    })

@app.route('/app')
def serve_app():
    """Sirve la aplicación web desde static/index.html"""
    try:
        from flask import send_from_directory
        return send_from_directory('static', 'index.html')
    except Exception:
        return jsonify({"error": "Frontend no encontrado"}), 404


@app.route('/admin/conversations', methods=['GET'])
def get_all_conversations():
    """
    Obtiene todas las conversaciones con información completa para el CMS.
    Parámetros opcionales:
    - limit: número de conversaciones (default: 50)
    - offset: para paginación (default: 0)
    - search: buscar por nombre, correo o contenido
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', '', type=str).lower()
        
        # Obtener todos los archivos JSON de sesiones
        session_files = glob.glob('chatsessions/session_*.json')
        session_files.sort(key=os.path.getmtime, reverse=True)  # Más recientes primero
        
        conversations = []
        
        for file_path in session_files[offset:]:
            if len(conversations) >= limit:
                break
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                # Extraer información básica
                user_info = session_data.get('user', {})
                history = session_data.get('history', [])
                
                # Aplicar filtro de búsqueda si existe
                if search:
                    searchable_text = (
                        user_info.get('nombre', '').lower() + ' ' +
                        user_info.get('correo', '').lower() + ' ' +
                        ' '.join([msg.get('content', '') for msg in history]).lower()
                    )
                    if search not in searchable_text:
                        continue
                
                # Calcular estadísticas
                user_messages = [msg for msg in history if msg.get('role') == 'user']
                assistant_messages = [msg for msg in history if msg.get('role') == 'assistant']
                
                # Obtener timestamps
                first_message_time = None
                last_message_time = None
                if history:
                    first_message_time = history[0].get('timestamp')
                    last_message_time = history[-1].get('timestamp')
                
                conversation_summary = {
                    "session_id": user_info.get('session_id', ''),
                    "file_name": os.path.basename(file_path),
                    "user": {
                        "id": user_info.get('id', ''),
                        "nombre": user_info.get('nombre', ''),
                        "correo": user_info.get('correo', ''),
                        "whatsapp": user_info.get('whatsapp', '')
                    },
                    "conversation_stats": {
                        "total_messages": len(history),
                        "user_messages": len(user_messages),
                        "assistant_messages": len(assistant_messages),
                        "first_message": first_message_time,
                        "last_message": last_message_time
                    },
                    "last_user_message": user_messages[-1].get('content', '')[:100] + '...' if user_messages else '',
                    "file_modified": datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
                }
                
                conversations.append(conversation_summary)
                
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error leyendo archivo {file_path}: {str(e)}")
                continue
        
        return jsonify({
            "success": True,
            "conversations": conversations,
            "total_files": len(session_files),
            "returned": len(conversations),
            "pagination": {
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < len(session_files)
            }
        })
        
    except Exception as e:
        logger.error(f"Error obteniendo todas las conversaciones: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/admin/conversation/<session_id>/full', methods=['GET'])
def get_full_conversation(session_id):
    """
    Obtiene la conversación completa con todos los detalles para el CMS.
    Devuelve exactamente el mismo formato que está en el archivo JSON.
    """
    try:
        file_path = f'chatsessions/{session_id}.json'
        
        if not os.path.exists(file_path):
            return jsonify({"error": "Conversación no encontrada"}), 404
        
        with open(file_path, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        # Agregar metadatos del archivo
        file_stats = os.stat(file_path)
        session_data['file_metadata'] = {
            "file_name": f"{session_id}.json",
            "file_size": file_stats.st_size,
            "created": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(file_stats.st_mtime).isoformat()
        }
        
        return jsonify({
            "success": True,
            "session_data": session_data
        })
        
    except json.JSONDecodeError:
        return jsonify({"error": "Error al leer el archivo JSON"}), 500
    except Exception as e:
        logger.error(f"Error obteniendo conversación completa: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/admin/conversations/search', methods=['GET'])
def search_conversations():
    """
    Busca en todas las conversaciones por contenido específico.
    Parámetros:
    - q: término de búsqueda
    - field: campo específico (nombre, correo, whatsapp, content)
    - limit: número de resultados
    """
    try:
        query = request.args.get('q', '').lower().strip()
        field = request.args.get('field', 'all')
        limit = request.args.get('limit', 20, type=int)
        
        if not query:
            return jsonify({"error": "Parámetro 'q' es requerido"}), 400
        
        session_files = glob.glob('chatsessions/session_*.json')
        results = []
        
        for file_path in session_files:
            if len(results) >= limit:
                break
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                user_info = session_data.get('user', {})
                history = session_data.get('history', [])
                
                # Determinar si coincide con la búsqueda
                match_found = False
                match_details = []
                
                if field == 'all' or field == 'nombre':
                    if query in user_info.get('nombre', '').lower():
                        match_found = True
                        match_details.append(f"Nombre: {user_info.get('nombre', '')}")
                
                if field == 'all' or field == 'correo':
                    if query in user_info.get('correo', '').lower():
                        match_found = True
                        match_details.append(f"Correo: {user_info.get('correo', '')}")
                
                if field == 'all' or field == 'whatsapp':
                    if query in user_info.get('whatsapp', ''):
                        match_found = True
                        match_details.append(f"WhatsApp: {user_info.get('whatsapp', '')}")
                
                if field == 'all' or field == 'content':
                    for msg in history:
                        if query in msg.get('content', '').lower():
                            match_found = True
                            content_preview = msg.get('content', '')[:100] + '...'
                            match_details.append(f"Mensaje ({msg.get('role', '')}): {content_preview}")
                            break
                
                if match_found:
                    results.append({
                        "session_id": user_info.get('session_id', ''),
                        "file_name": os.path.basename(file_path),
                        "user": user_info,
                        "matches": match_details,
                        "total_messages": len(history)
                    })
                    
            except (json.JSONDecodeError, IOError) as e:
                continue
        
        return jsonify({
            "success": True,
            "query": query,
            "field": field,
            "results": results,
            "total_found": len(results)
        })
        
    except Exception as e:
        logger.error(f"Error en búsqueda: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route('/admin/stats', methods=['GET'])
def get_conversation_stats():
    """
    Obtiene estadísticas generales de todas las conversaciones.
    """
    try:
        session_files = glob.glob('chatsessions/session_*.json')
        
        total_conversations = len(session_files)
        total_messages = 0
        total_users = set()
        date_range = {"earliest": None, "latest": None}
        
        for file_path in session_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                user_info = session_data.get('user', {})
                history = session_data.get('history', [])
                
                total_messages += len(history)
                if user_info.get('correo'):
                    total_users.add(user_info.get('correo'))
                
                # Actualizar rango de fechas
                for msg in history:
                    timestamp = msg.get('timestamp')
                    if timestamp:
                        if not date_range["earliest"] or timestamp < date_range["earliest"]:
                            date_range["earliest"] = timestamp
                        if not date_range["latest"] or timestamp > date_range["latest"]:
                            date_range["latest"] = timestamp
                            
            except (json.JSONDecodeError, IOError):
                continue
        
        return jsonify({
            "success": True,
            "stats": {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "unique_users": len(total_users),
                "average_messages_per_conversation": round(total_messages / max(total_conversations, 1), 2),
                "date_range": date_range
            }
        })
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}", exc_info=True)
        return jsonify({"error": "Error interno del servidor"}), 500

# En app.py, reemplaza la sección if __name__ == '__main__': con este código:

if __name__ == '__main__':
    initialize_app()
    
    # Para Easypanel - usar el puerto exacto de la variable de entorno
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0'
    
    # Log detallado para debugging
    logger.info(f"🌐 Iniciando servidor en {host}:{port}")
    logger.info(f"🔧 PORT env var: {os.environ.get('PORT', 'No definida')}")
    logger.info(f"🔧 FLASK_ENV: {os.environ.get('FLASK_ENV', 'No definida')}")
    
    # Configuración para producción
    app.run(
        host=host, 
        port=port, 
        debug=False, 
        threaded=True,
        use_reloader=False  # Importante para producción
    )
