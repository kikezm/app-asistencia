import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import os
import streamlit_javascript as st_js # Nueva librería para detectar dispositivo

# --- CONFIGURACIÓN Y CONEXIÓN A GOOGLE ---
def conectar_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    elif os.path.exists('credentials.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    else:
        st.error("⚠️ Error de credenciales.")
        st.stop()
    
    client = gspread.authorize(creds)
    sheet = client.open("Base de Datos Asistencia").sheet1 
    return sheet

# --- FUNCIÓN PARA REGISTRAR ---
def registrar_fichaje(nombre, tipo, info_dispositivo):
    try:
        sheet = conectar_google_sheets()
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M:%S")
        
        # Guardamos: Fecha, Hora, Nombre, Tipo, Dispositivo
        sheet.append_row([fecha, hora, nombre, tipo, info_dispositivo])
        
        st.success(f"✅ {tipo} registrada para {nombre}")
        time.sleep(2)
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Error guardando datos: {e}")

# --- INTERFAZ ---
st.set_page_config(page_title="Control Asistencia", page_icon="🕒")

# Obtener información del navegador (User Agent) con JavaScript
ua_string = st_js.st_javascript("navigator.userAgent")

# Detectar usuario desde el enlace (URL)
# Busca si hay un ?empleado=Juan en la url
params = st.query_params
usuario_url = params.get("empleado", None)

st.title("🕒 Control de Asistencia")

# LÓGICA DE USUARIO
if usuario_url:
    # --- MODO EMPLEADO (Enlace personalizado) ---
    st.info(f"👋 Hola, **{usuario_url}**")
    st.write("Registra tu movimiento:")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🟢 ENTRADA", use_container_width=True):
            registrar_fichaje(usuario_url, "ENTRADA", ua_string)
    with col2:
        if st.button("🔴 SALIDA", use_container_width=True):
            registrar_fichaje(usuario_url, "SALIDA", ua_string)

else:
    # --- MODO GENERAL / ADMIN ---
    menu = ["Panel Admin", "Generador de Enlaces"]
    opcion = st.sidebar.selectbox("Menú", menu)
    
    if opcion == "Generador de Enlaces":
        st.subheader("🔗 Crear enlace para trabajador")
        st.write("Escribe el nombre del trabajador para generar su enlace único.")
        nuevo_nombre = st.text_input("Nombre del Empleado")
        
        if nuevo_nombre:
            # Crea la URL base (truco para saber la url actual)
            base_url = "https://app-asistencia.streamlit.app" # CAMBIA ESTO SI TU URL ES OTRA
            link = f"{base_url}/?empleado={nuevo_nombre}"
            st.code(link, language="text")
            st.caption("Copia este enlace y envíaselo por WhatsApp a ese trabajador.")

    elif opcion == "Panel Admin":
        st.subheader("🕵️ Panel de Control")
        password = st.text_input("Contraseña", type="password")
        
        if password == "admin123":
            try:
                sheet = conectar_google_sheets()
                datos = sheet.get_all_records()
                df = pd.DataFrame(datos)
                
                st.write("### Últimos fichajes")
                st.dataframe(df.tail(5))
                
                # Descarga
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Descargar Todo", csv, "asistencia.csv", "text/csv")
            except:
                st.warning("No hay datos o error de conexión.")
