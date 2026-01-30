import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import os
import streamlit_javascript as st_js
import urllib.parse # <--- NUEVA LIBRERÍA PARA ARREGLAR ESPACIOS
import io

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
            st.subheader("🕵️ Panel de Control y Nóminas")
            
            password = st.text_input("Contraseña de Acceso", type="password")
            
            if password == "admin123": # <--- Tu contraseña
                try:
                    sheet = conectar_google_sheets()
                    datos = sheet.get_all_records()
                    
                    if datos:
                        df = pd.DataFrame(datos)
                        
                        # Procesamiento de fechas
                        df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S')
                        df = df.sort_values(by='FechaHora')
                        
                        st.write("---")
                        st.write("### 📊 Informe Excel")
                        
                        lista_empleados = list(df['Empleado'].unique())
                        empleado_selec = st.selectbox("Selecciona Empleado:", lista_empleados)
                        
                        if empleado_selec:
                            df_emp = df[df['Empleado'] == empleado_selec].copy()
                            
                            # --- CÁLCULO DE HORAS ---
                            resumen_data = []
                            entrada_temp = None
                            dias_unicos = df_emp['Fecha'].unique()
                            total_seconds = 0
                            
                            for dia in dias_unicos:
                                movimientos_dia = df_emp[df_emp['Fecha'] == dia].sort_values(by='FechaHora')
                                segundos_dia = 0
                                entrada_pendiente = None
                                
                                for index, row in movimientos_dia.iterrows():
                                    if row['Tipo'] == 'ENTRADA':
                                        entrada_pendiente = row['FechaHora']
                                    elif row['Tipo'] == 'SALIDA' and entrada_pendiente is not None:
                                        diferencia = row['FechaHora'] - entrada_pendiente
                                        segundos_dia += diferencia.total_seconds()
                                        entrada_pendiente = None
                                
                                # Formato horas:minutos
                                horas = int(segundos_dia // 3600)
                                minutos = int((segundos_dia % 3600) // 60)
                                
                                total_seconds += segundos_dia
                                
                                resumen_data.append({
                                    "Fecha": dia,
                                    "Horas Trabajadas": f"{horas}h {minutos}m",
                                    "Detalle": f"{horas}:{minutos:02d}" # Formato útil para Excel
                                })
                            
                            df_resumen = pd.DataFrame(resumen_data)
                            
                            # Totales generales
                            tot_h = int(total_seconds // 3600)
                            tot_m = int((total_seconds % 3600) // 60)
                            
                            st.info(f"Resumen para **{empleado_selec}**: {tot_h}h {tot_m}m totales.")
                            
                            # --- GENERACIÓN DEL EXCEL (En Memoria) ---
                            buffer = io.BytesIO()
                            
                            # Usamos ExcelWriter para crear múltiples hojas
                            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                # Hoja 1: El Resumen limpio
                                df_resumen.to_excel(writer, sheet_name='Resumen Horas', index=False)
                                
                                # Hoja 2: Los datos crudos (auditoría)
                                # Limpiamos columnas que no sirven para el reporte
                                df_emp_clean = df_emp[['Fecha', 'Hora', 'Tipo', 'Dispositivo']]
                                df_emp_clean.to_excel(writer, sheet_name='Detalle Fichajes', index=False)
                                
                            # Preparamos el archivo para descargar
                            buffer.seek(0)
                            
                            st.download_button(
                                label=f"📥 Descargar Excel de {empleado_selec}",
                                data=buffer,
                                file_name=f"Asistencia_{empleado_selec}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )

                    else:
                        st.warning("La base de datos está vacía.")
                except Exception as e:
                    st.error(f"Error: {e}")
