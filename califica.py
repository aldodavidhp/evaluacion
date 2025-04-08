import streamlit as st
import os
import tempfile
from PyPDF2 import PdfReader
from docx import Document
import google.generativeai as genai
from PIL import Image

# Configuración de la página
st.set_page_config(page_title="Evaluador de Trabajos", page_icon="📝", layout="wide")

# Configuración de Gemini AI (con API Key incluida)
genai.configure(api_key="AIzaSyAtsIgmN8GWnuy-tUhPIt9odwouOvMuujc")
model = genai.GenerativeModel('gemini-1.5-flash')  # Modelo actualizado

# Título de la aplicación
st.title("📝 Evaluador de Trabajos con Gemini AI")
st.markdown("""
Sube los criterios de evaluación en PDF y los trabajos de los alumnos (PDF o Word) para obtener 
una evaluación automatizada con retroalimentación detallada usando Gemini AI.
""")

# Sidebar para configuración
with st.sidebar:
    st.header("Configuración")
    
    # Sliders para ajustar el comportamiento de la IA
    temperature = st.slider("Creatividad de las evaluaciones", 0.0, 1.0, 0.5, help="Valores más altos = respuestas más creativas pero menos precisas")
    max_tokens = st.slider("Longitud máxima de respuestas", 100, 2000, 1200, help="Controla cuán detalladas serán las evaluaciones")
    
    st.divider()
    st.info("""
    **Instrucciones:**
    1. Sube los criterios de evaluación en PDF
    2. Sube los trabajos de los estudiantes (PDF o Word)
    3. Revisa las evaluaciones generadas automáticamente
    """)

# Función para extraer texto de PDF
def extract_text_from_pdf(pdf_file):
    text = ""
    pdf_reader = PdfReader(pdf_file)
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

# Función para extraer texto de Word
def extract_text_from_word(word_file):
    doc = Document(word_file)
    return "\n".join([para.text for para in doc.paragraphs])

# Función para procesar archivos de alumnos
def process_student_file(file):
    try:
        if file.type == "application/pdf":
            return extract_text_from_pdf(file)
        elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return extract_text_from_word(file)
        else:
            return None
    except Exception as e:
        st.error(f"Error procesando archivo {file.name}: {str(e)}")
        return None

# Función para evaluar con Gemini
def evaluate_with_gemini(criteria, student_work, student_name=""):
    prompt = f"""
    Eres un profesor universitario experto en evaluación de trabajos académicos. 
    A continuación te proporciono los criterios de evaluación y el trabajo de un estudiante o docente.
    
    **CRITERIOS DE EVALUACIÓN:**
    {criteria}
    
    **TRABAJO DEL ESTUDIANTE O DOCENTE {student_name.upper() if student_name else ''}:**
    {student_work}
    
    Proporciona una evaluación detallada que incluya:
    
    
    1. **PUNTOS FUERTES** (3-5 aspectos bien desarrollados)
    2. **ÁREAS DE MEJORA** (3-5 aspectos a mejorar con sugerencias concretas)
    3. **COMENTARIOS FINALES** (retroalimentación constructiva y motivadora)
    
    Usa un tono profesional pero cercano, destacando los logros y ofreciendo guía para mejorar.
    Organiza la respuesta con encabezados claros y bullet points para mejor legibilidad.
   
    """
    
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                top_p=0.9
            )
        )
        return response.text
    except Exception as e:
        return f"Error al evaluar: {str(e)}"

# Interfaz principal
tab1, tab2 = st.tabs(["📋 Subir Criterios", "🧑‍🎓 Evaluar Trabajos"])

with tab1:
    st.header("Criterios de Evaluación")
    criteria_file = st.file_uploader("Sube el PDF con los criterios de evaluación", type=["pdf"], 
                                   help="El archivo debe contener los rubros, puntajes y estándares de evaluación")
    
    if criteria_file:
        with st.spinner("Procesando criterios de evaluación..."):
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(criteria_file.getvalue())
                criteria_text = extract_text_from_pdf(tmp.name)
            
            st.session_state.criteria_text = criteria_text
            st.success("✅ Criterios cargados correctamente!")
            
            st.subheader("Vista previa de los criterios")
            st.text_area("Contenido extraído", criteria_text, height=300, disabled=True, 
                        label_visibility="collapsed")

with tab2:
    st.header("Evaluar Trabajos de Estudiantes")
    
    if 'criteria_text' not in st.session_state:
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
            
            for i, file in enumerate(student_files):
                progress_bar.progress((i + 1) / total_files, f"Procesando {i+1}/{total_files}: {file.name}")
                
                with st.expander(f"📄 {file.name}", expanded=i==0):
                    with st.spinner(f"Analizando {file.name}..."):
                        student_text = process_student_file(file)
                        
                        if student_text:
                            # Extraer nombre del archivo sin extensión para personalización
                            student_name = os.path.splitext(file.name)[0]
                            
                            col1, col2 = st.columns([1, 2])
                            
                            with col1:
                                st.subheader("📋 Contenido del Trabajo")
                                st.text_area(f"Contenido {file.name}", student_text[:5000] + ("..." if len(student_text) > 5000 else ""), 
                                            height=300, disabled=True, label_visibility="collapsed")
                                st.caption(f"Mostrando primeros 5000 caracteres de {len(student_text)} totales")
                            
                            with col2:
                                st.subheader("📝 Evaluación Automática")
                                evaluation = evaluate_with_gemini(st.session_state.criteria_text, student_text, student_name)
                                st.markdown(evaluation)
                                
                                # Opción para descargar la evaluación
                                st.download_button(
                                    label="⬇️ Descargar Evaluación Completa",
                                    data=evaluation,
                                    file_name=f"Evaluacion_{student_name}.txt",
                                    mime="text/plain",
                                    key=f"download_{i}",
                                    help="Descarga esta evaluación como archivo de texto"
                                )
                        else:
                            st.error(f"❌ No se pudo procesar el archivo {file.name}")

            progress_bar.empty()
            st.success(f"✅ Procesamiento completado! {total_files} trabajos evaluados")
