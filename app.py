import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import os
import streamlit_javascript as st_js
import urllib.parse # <--- NUEVA LIBRERÍA PARA ARREGLAR ESPACIOS

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
        
        sheet.append_row([fecha, hora, nombre, tipo, info_dispositivo])
        
        st.success(f"✅ {tipo} registrada para {nombre}")
        time.sleep(2)
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Error guardando datos: {e}")

# --- INTERFAZ ---
st.set_page_config(page_title="Control Asistencia", page_icon="🕒")

try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

# Captura el parámetro y arregla los caracteres especiales
params = st.query_params
usuario_url = params.get("empleado", None)

st.title("🕒 Control de Asistencia")

if usuario_url:
    # --- MODO EMPLEADO ---
    st.info(f"👋 Hola, **{usuario_url}**")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🟢 ENTRADA", use_container_width=True):
            registrar_fichaje(usuario_url, "ENTRADA", ua_string)
    with col2:
        if st.button("🔴 SALIDA", use_container_width=True):
            registrar_fichaje(usuario_url, "SALIDA", ua_string)

else:
    # --- MODO ADMIN ---
    menu = ["Panel Admin", "Generador de Enlaces"]
    opcion = st.sidebar.selectbox("Menú", menu)
    
    if opcion == "Generador de Enlaces":
        st.subheader("🔗 Crear enlace seguro")
        nuevo_nombre = st.text_input("Nombre y Apellidos del Empleado")
        
        # --- AQUÍ ES DONDE DEBES PONER TU URL REAL ---
        # Borra la de abajo y pega la tuya:
        MI_URL_REAL = "https://app-asistencia-dknejmfedu4pswfrqf7prc.streamlit.app/" 
        
        if nuevo_nombre:
            # Esto convierte "María Serrano" en "Mar%C3%ADa%20Serrano"
            nombre_seguro = urllib.parse.quote(nuevo_nombre)
            link = f"{MI_URL_REAL}/?empleado={nombre_seguro}"
            
            st.success("Enlace generado correctamente (sin espacios):")
            st.code(link, language="text")
            st.caption("Copia este enlace y envíaselo al trabajador.")
    elif opcion == "Panel Admin":
            st.subheader("🕵️ Panel de Control")
            
            # --- CAMBIA TU CONTRASEÑA AQUÍ ---
            password = st.text_input("Contraseña de Acceso", type="password")
            
            if password == "1234": # <--- Pon aquí tu contraseña real
                try:
                    sheet = conectar_google_sheets()
                    datos = sheet.get_all_records()
                    
                    if datos:
                        df = pd.DataFrame(datos)
                        
                        # --- FILTROS DE INFORME ---
                        st.write("---")
                        st.write("### 📊 Generar Informe")
                        
                        col_filtro1, col_filtro2 = st.columns(2)
                        
                        with col_filtro1:
                            # Filtro por Empleado
                            lista_empleados = ["Todos"] + list(df['Empleado'].unique())
                            filtro_empleado = st.selectbox("Filtrar por Empleado:", lista_empleados)
                        
                        with col_filtro2:
                            # Filtro por Tipo (Entrada/Salida) - Opcional
                            filtro_tipo = st.selectbox("Tipo de movimiento:", ["Todos", "ENTRADA", "SALIDA"])
                        
                        # Aplicar filtros
                        df_final = df.copy()
                        if filtro_empleado != "Todos":
                            df_final = df_final[df_final['Empleado'] == filtro_empleado]
                        if filtro_tipo != "Todos":
                            df_final = df_final[df_final['Tipo'] == filtro_tipo]
                        
                        # Mostrar vista previa
                        st.write(f"Mostrando {len(df_final)} registros:")
                        st.dataframe(df_final)
                        
                        # Botón de Descarga
                        csv = df_final.to_csv(index=False).encode('utf-8')
                        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                        nombre_archivo = f"informe_{filtro_empleado}_{fecha_hoy}.csv"
                        
                        st.download_button(
                            label="📥 Descargar Informe Filtrado",
                            data=csv,
                            file_name=nombre_archivo,
                            mime="text/csv"
                        )
                    else:
                        st.warning("La base de datos está vacía.")
                except Exception as e:
                    st.error(f"Error cargando datos: {e}")

