import streamlit as st
import os
import tempfile
import json
import pandas as pd # Se añade para la gestión de datos y CSV
from PyPDF2 import PdfReader
from docx import Document
import google.generativeai as genai
from PIL import Image

# Configuración de la página
st.set_page_config(page_title="Evaluador de Trabajos", page_icon="📝", layout="wide")

# Configuración de Gemini AI (con API Key incluida)
# ATENCIÓN: Por seguridad, se recomienda encarecidamente usar st.secrets en lugar de poner la clave
# directamente en el código.
# Si estás ejecutando esto en un entorno sin st.secrets, coloca tu clave aquí:
genai.configure(api_key="AIzaSyAtsIgmN8GWnuy-tUhPIt9odwouOvMuujc")
model = genai.GenerativeModel('gemini-2.5-flash')

# Esquema JSON para la respuesta estructurada del modelo
# Esto asegura que obtenemos datos limpios para el CSV.
EVALUATION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "Nombre_Estudiante": {"type": "STRING", "description": "El nombre completo del estudiante extraído del contenido del trabajo. Si no se encuentra, devolver 'No encontrado'."},
        "I_ElementosCurriculares": {"type": "STRING", "description": "Puntaje o nivel de logro para 'I. Elementos Curriculares y Contexto'"},
        "II_SecuenciaDidactica": {"type": "STRING", "description": "Puntaje o nivel de logro para 'II. Secuencia Didáctica JUMP Math'"},
        "III_PrincipiosDidacticos": {"type": "STRING", "description": "Puntaje o nivel de logro para 'III. Aplicación de Principios Didácticos JUMP Math'"},
        "IV_InstrumentosEvaluacion": {"type": "STRING", "description": "Puntaje o nivel de logro para 'IV. Instrumentos de Evaluación'"},
        "V_EvidenciasImplementacion": {"type": "STRING", "description": "Puntaje o nivel de logro para 'V. Evidencias de Implementación (Anexo)'"},
        "Total_Calculado": {"type": "STRING", "description": "El puntaje total final o la evaluación general (ej: '18/20' o 'Sobresaliente')."},
        "Retroalimentacion_Corta": {"type": "STRING", "description": "Un resumen conciso y motivador de los comentarios finales (máximo 200 caracteres)"},
        "Evaluacion_Completa_Markdown": {"type": "STRING", "description": "El texto completo y detallado de la evaluación, incluyendo Puntos Fuertes, Áreas de Mejora y Comentarios Finales en formato Markdown."}
    },
    "required": [
        "Nombre_Estudiante", "I_ElementosCurriculares", "II_SecuenciaDidactica", "III_PrincipiosDidacticos",
        "IV_InstrumentosEvaluacion", "V_EvidenciasImplementacion", "Total_Calculado",
        "Retroalimentacion_Corta", "Evaluacion_Completa_Markdown"
    ]
}


# Título de la aplicación
st.title("📝 Evaluador de Trabajos con Gemini AI")
st.markdown("""
Sube los criterios de evaluación en PDF y los trabajos de los alumnos (PDF o Word) para obtener
una evaluación automatizada con retroalimentación detallada **y un resumen de calificaciones en formato CSV**.
""")

# Sidebar para configuración
with st.sidebar:
    st.header("Configuración")
    
    # Sliders para ajustar el comportamiento de la IA
    temperature = st.slider("Creatividad de las evaluaciones", 0.0, 1.0, 0.5, help="Valores más altos = respuestas más creativas pero menos precisas")
    # Se reduce el max_tokens aquí, ya que la longitud total ahora incluye el JSON y el texto.
    max_tokens = st.slider("Longitud máxima de respuestas", 100, 8000, 4000, help="Controla cuán detalladas serán las evaluaciones. Se ha aumentado el límite para evitar que las respuestas se corten.")
    
    st.divider()
    st.info("""
    **Instrucciones:**
    1. Sube los criterios de evaluación en PDF
    2. Sube los trabajos de los estudiantes (PDF o Word)
    3. Revisa las evaluaciones generadas automáticamente y **descarga el CSV**.
    """)

# Inicializar resultados de evaluación en el estado de la sesión
if 'evaluation_results' not in st.session_state:
    st.session_state.evaluation_results = []

# Función para extraer texto de PDF
def extract_text_from_pdf(pdf_file):
    text = ""
    pdf_reader = PdfReader(pdf_file)
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text

# Función para extraer texto de Word
def extract_text_from_word(word_file):
    doc = Document(word_file)
    return "\n".join([para.text for para in doc.paragraphs])

# Función para procesar archivos de alumnos
def process_student_file(file):
    try:
        # Crea un archivo temporal para que PyPDF2 o docx lean el contenido binario
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file.getvalue())
            tmp_path = tmp.name

        if file.type == "application/pdf":
            return extract_text_from_pdf(tmp_path)
        elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return extract_text_from_word(tmp_path)
        else:
            return None
    except Exception as e:
        st.error(f"Error procesando archivo {file.name}: {str(e)}")
        return None
    finally:
        # Asegurarse de eliminar el archivo temporal
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)

# Función para evaluar con Gemini, ahora retorna JSON
def evaluate_with_gemini(criteria, student_work, student_name=""):
    """
    Evalúa el trabajo y retorna la evaluación detallada (Markdown) y los datos estructurados (JSON).
    """
    prompt = f"""
    Emanando como un profesor universitario experto en evaluación de trabajos académicos, tu tarea es doble:
    1. Evaluar el trabajo con respecto a los CRITERIOS.
    2. Generar el resultado estrictamente en formato JSON, siguiendo el esquema proporcionado.

    **CRITERIOS DE EVALUACIÓN:**
    {criteria}

    **TRABAJO DEL ESTUDIANTE O DOCENTE {student_name.upper() if student_name else ''}:**
    {student_work}

    **INSTRUCCIONES PARA EL JSON:**
    * Para la clave 'Nombre_Estudiante', extrae el nombre completo del autor o estudiante del texto del trabajo. Si no es posible identificarlo, usa el valor 'Nombre no encontrado'.
    * Para las claves 'I' a 'V', asigna un Nivel de Logro o Puntaje basado en los criterios y el trabajo.
    * Para 'Total_Calculado', proporciona el puntaje o la calificación final.
    * Para 'Retroalimentacion_Corta', escribe el resumen conciso (MÁXIMO 200 CARACTERES) y motivador.
    * Para 'Evaluacion_Completa_Markdown', escribe la evaluación detallada, organizada con encabezados claros y bullet points, que incluya:
        1. **PUNTOS FUERTES** (1-3 aspectos bien desarrollados)
        2. **ÁREAS DE MEJORA** (1-3 aspectos a mejorar con sugerencias concretas)
        3. **COMENTARIOS FINALES** (retroalimentación constructiva y motivadora)
    
    """
    
    # Se definen configuraciones de seguridad para evitar bloqueos por falsos positivos.
    # ATENCIÓN: Esto deshabilita los filtros de contenido dañino. Usar con precaución.
    safety_settings = {
        "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
    }

    try:
        full_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "response_mime_type": "application/json",
            "response_schema": EVALUATION_SCHEMA
        }
        
        response = model.generate_content(
            prompt, 
            generation_config=full_config,
            safety_settings=safety_settings  # Se añaden las configuraciones de seguridad
        )

        try:
            structured_data = json.loads(response.text)
            full_evaluation = structured_data.get("Evaluacion_Completa_Markdown", "Error al extraer la evaluación detallada.")
            return full_evaluation, structured_data
        except json.JSONDecodeError as e:
            st.error(f"La respuesta para '{student_name}' no es un JSON válido. El modelo puede haber fallado en seguir las instrucciones. Error: {e}")
            st.text_area("Respuesta recibida del modelo (JSON inválido):", response.text)
            return "Error de formato JSON", None
        except ValueError:
            # Este error ahora es menos probable, pero se mantiene por si la respuesta viene vacía por otras razones.
            st.error(f"La respuesta para '{student_name}' está vacía o no se pudo procesar. Razón: {response.prompt_feedback}")
            return f"Respuesta vacía o bloqueada", None
        
    except Exception as e:
        # Captura otros errores como problemas de autenticación (API Key) o de red.
        st.error(f"Ocurrió un error al contactar a la API de Gemini para {student_name}: {str(e)}")
        return f"Error en la llamada a la API: {str(e)}", None

# Interfaz principal
tab1, tab2 = st.tabs(["📋 Subir Criterios", "🧑‍🎓 Evaluar Trabajos"])

with tab1:
    st.header("Criterios de Evaluación")
    criteria_file = st.file_uploader("Sube el PDF con los criterios de evaluación", type=["pdf"],
                                     help="El archivo debe contener los rubros, puntajes y estándares de evaluación")
    
    if criteria_file:
        with st.spinner("Procesando criterios de evaluación..."):
            
            criteria_text = extract_text_from_pdf(criteria_file)
            
            st.session_state.criteria_text = criteria_text
            st.success("✅ Criterios cargados correctamente!")
            
            st.subheader("Vista previa de los criterios")
            st.text_area("Contenido extraído", criteria_text, height=300, disabled=True,
                         label_visibility="collapsed")

with tab2:
    st.header("Evaluar Trabajos de Estudiantes")
    
    if 'criteria_text' not in st.session_state or not st.session_state.criteria_text:
        st.warning("⚠️ Por favor sube primero los criterios de evaluación en la pestaña 'Subir Criterios'")
    else:
        student_files = st.file_uploader(
            "Sube los trabajos de los estudiantes (PDF o Word)",
            type=["pdf", "docx"],
            accept_multiple_files=True,
            help="Puedes seleccionar múltiples archivos a la vez"
        )
        
        if student_files:
            progress_bar = st.progress(0)
            total_files = len(student_files)
            
            # Limpiar resultados anteriores antes de un nuevo proceso
            st.session_state.evaluation_results = []
            
            for i, file in enumerate(student_files):
                progress_bar.progress((i + 1) / total_files, f"Procesando {i+1}/{total_files}: {file.name}")
                
                with st.expander(f"📄 {file.name}", expanded=i==0):
                    with st.spinner(f"Analizando {file.name}..."):
                        student_text = process_student_file(file)
                        
                        if student_text:
                            # Extraer nombre del archivo sin extensión
                            student_name = os.path.splitext(file.name)[0]
                            
                            # Evaluar y obtener tanto el markdown como el JSON
                            evaluation_markdown, structured_result = evaluate_with_gemini(
                                st.session_state.criteria_text, student_text, student_name
                            )
                            
                            if structured_result:
                                # Preparar y almacenar la fila de datos para el CSV
                                csv_data = {
                                    "Nombre": structured_result.get("Nombre_Estudiante", student_name),
                                    "I. Elementos Curriculares y Contexto (Plantilla)": structured_result.get("I_ElementosCurriculares", "N/A"),
                                    "II. Secuencia Didáctica JUMP Math (Metodología)": structured_result.get("II_SecuenciaDidactica", "N/A"),
                                    "III. Aplicación de Principios Didácticos JUMP Math": structured_result.get("III_PrincipiosDidacticos", "N/A"),
                                    "IV. Instrumentos de Evaluación": structured_result.get("IV_InstrumentosEvaluacion", "N/A"),
                                    "V. Evidencias de Implementación (Anexo)": structured_result.get("V_EvidenciasImplementacion", "N/A"),
                                    "Total": structured_result.get("Total_Calculado", "N/A"),
                                    "Retroalimentación": structured_result.get("Retroalimentacion_Corta", "N/A"),
                                }
                                st.session_state.evaluation_results.append(csv_data)
                                
                                # Mostrar la evaluación detallada
                                col1, col2 = st.columns([1, 2])
                                with col1:
                                    st.subheader("📋 Contenido del Trabajo")
                                    st.text_area(f"Contenido {file.name}", student_text[:5000] + ("..." if len(student_text) > 5000 else ""),
                                                 height=300, disabled=True, label_visibility="collapsed")
                                    st.caption(f"Mostrando primeros 5000 caracteres de {len(student_text)} totales")
                                    
                                with col2:
                                    st.subheader("📝 Evaluación Automática")
                                    st.markdown(evaluation_markdown)
                                    
                                    # Opción para descargar la evaluación completa (TXT)
                                    st.download_button(
                                        label="⬇️ Descargar Evaluación Completa (TXT)",
                                        data=evaluation_markdown,
                                        file_name=f"Evaluacion_{student_name}.txt",
                                        mime="text/plain",
                                        key=f"download_txt_{i}",
                                        help="Descarga esta evaluación detallada como archivo de texto"
                                    )
                            else:
                                st.error(f"❌ No se pudo obtener la evaluación estructurada para {file.name}")
                        else:
                            st.error(f"❌ No se pudo procesar el archivo {file.name}")

            progress_bar.empty()
            st.success(f"✅ Procesamiento completado! {total_files} trabajos evaluados")
            
            # --- Generación y Descarga de CSV (Después de procesar todos los archivos) ---
            if st.session_state.evaluation_results:
                st.divider()
                st.subheader("📊 Resumen de Evaluaciones (TXT para Excel)")
                
                # Crear DataFrame y mostrarlo
                df = pd.DataFrame(st.session_state.evaluation_results)
                st.dataframe(df, use_container_width=True)
                
                # Generar CSV para descarga.
                # Nota: La codificación 'utf-8' puede dar problemas de acentos en algunas versiones de Excel.
                csv_output = df.to_csv(index=False, encoding='utf-8')
                
                st.download_button(
                    label="⬇️ Descargar Tabla de Calificaciones (CSV)",
                    data=csv_output,
                    file_name='resumen_evaluaciones_gemini.csv', # Extensión .csv
                    mime='text/csv', # MIME type para CSV
                    help="Descarga un archivo CSV con el resumen de las calificaciones."
                )
