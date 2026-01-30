import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import os
import streamlit_javascript as st_js
import io
import uuid # Librería para generar códigos secretos únicos

# --- CONFIGURACIÓN Y CONEXIÓN ---
def conectar_google_sheets(nombre_hoja):
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
    # Abrimos el archivo y seleccionamos la pestaña específica
    try:
        sheet = client.open("Base de Datos Asistencia").worksheet(nombre_hoja)
        return sheet
    except gspread.WorksheetNotFound:
        st.error(f"❌ No encuentro la pestaña '{nombre_hoja}'. Por favor créala en Google Sheets.")
        st.stop()

# --- FUNCIONES DE LÓGICA ---

def registrar_fichaje(nombre, tipo, info_dispositivo):
    try:
        sheet = conectar_google_sheets("Hoja 1") # La hoja de registros (por defecto suele ser Hoja 1 o sheet1)
        # NOTA: Si cambiaste el nombre de la hoja de registros, ponlo aquí. Si es la primera, suele ser "Hoja 1" o "Sheet1"
        
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M:%S")
        
        sheet.append_row([fecha, hora, nombre, tipo, info_dispositivo])
        
        st.success(f"✅ {tipo} registrada correctamente para {nombre}")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error guardando datos: {e}")

def obtener_nombre_por_token(token):
    try:
        sheet_users = conectar_google_sheets("Usuarios")
        records = sheet_users.get_all_records()
        for row in records:
            if str(row['ID']) == str(token):
                return row['Nombre']
        return None
    except:
        return None

def crear_nuevo_usuario(nombre_empleado):
    try:
        sheet_users = conectar_google_sheets("Usuarios")
        # Generamos un ID único aleatorio
        nuevo_id = str(uuid.uuid4())
        sheet_users.append_row([nuevo_id, nombre_empleado])
        return nuevo_id
    except Exception as e:
        st.error(f"Error creando usuario: {e}")
        return None

# --- INTERFAZ ---
st.set_page_config(page_title="Control Asistencia", page_icon="🔒")

# Captura de user agent
try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

# Capturamos el token de la URL
params = st.query_params
token_acceso = params.get("token", None)

st.title("🔒 Control de Asistencia Seguro")

# --- LÓGICA DE ACCESO ---

if token_acceso:
    # 1. Validamos si el token existe en nuestra base de datos
    nombre_usuario = obtener_nombre_por_token(token_acceso)
    
    if nombre_usuario:
        st.info(f"👋 Hola, **{nombre_usuario}**")
        st.write("Registra tu movimiento:")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🟢 ENTRADA", use_container_width=True):
                registrar_fichaje(nombre_usuario, "ENTRADA", ua_string)
        with col2:
            if st.button("🔴 SALIDA", use_container_width=True):
                registrar_fichaje(nombre_usuario, "SALIDA", ua_string)
    else:
        st.error("⛔ ACCESO DENEGADO. El enlace no es válido o ha caducado.")

else:
    # --- MODO ADMIN ---
    st.sidebar.title("Administración")
    menu = ["Generar Usuarios", "Informes y Nóminas"]
    opcion = st.sidebar.radio("Ir a:", menu)
    
    # Login simple
    password = st.sidebar.text_input("Contraseña Admin", type="password")
    
    if password == "admin123": # <--- TU CONTRASEÑA
        
        # --- SECCIÓN 1: CREAR USUARIOS ---
        if opcion == "Generar Usuarios":
            st.header("👥 Gestión de Empleados")
            st.write("Da de alta un empleado para generar su enlace único y secreto.")
            
            with st.form("nuevo_empleado"):
                nuevo_nombre = st.text_input("Nombre Completo")
                submit = st.form_submit_button("Crear Empleado y Generar Enlace")
                
                if submit and nuevo_nombre:
                    token_generado = crear_nuevo_usuario(nuevo_nombre)
                    if token_generado:
                        # URL Base (cámbiala por la tuya real)
                        MI_URL = "https://tu-app-asistencia.streamlit.app" 
                        link_seguro = f"{MI_URL}/?token={token_generado}"
                        
                        st.success(f"✅ Usuario '{nuevo_nombre}' creado.")
                        st.write("Envía este enlace PERSONAL e INTRANSFERIBLE:")
                        st.code(link_seguro, language="text")
                        st.warning("Guarda este enlace, si se pierde tendrás que consultar la hoja 'Usuarios'.")

            st.write("---")
            st.write("### Usuarios Activos")
            try:
                sheet_u = conectar_google_sheets("Usuarios")
                st.dataframe(pd.DataFrame(sheet_u.get_all_records()))
            except:
                st.info("No hay usuarios creados.")

        # --- SECCIÓN 2: INFORMES (Igual que antes) ---
        elif opcion == "Informes y Nóminas":
            st.header("📊 Descarga de Informes")
            
            try:
                # OJO: Aquí conectamos a la hoja de registros (probablemente "Hoja 1")
                # Si tu pestaña de datos se llama "Sheet1" o de otra forma, revisa esto:
                sheet = conectar_google_sheets("Hoja 1") 
                datos = sheet.get_all_records()
                
                if datos:
                    df = pd.DataFrame(datos)
                    # (Lógica de informes idéntica a la anterior...)
                    # Procesamiento de fechas
                    df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S')
                    df = df.sort_values(by='FechaHora')
                    df['Mes_Año'] = df['FechaHora'].dt.strftime('%m/%Y')
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        lista_meses = sorted(df['Mes_Año'].unique().tolist(), reverse=True)
                        mes_seleccionado = st.selectbox("Mes:", lista_meses)
                    
                    df_mes = df[df['Mes_Año'] == mes_seleccionado].copy()
                    
                    with col2:
                        lista_empleados = ["TODOS (Resumen Global)"] + list(df_mes['Empleado'].unique())
                        empleado_selec = st.selectbox("Empleado:", lista_empleados)
                    
                    if st.button("Descargar Informe Excel"):
                        buffer = io.BytesIO()
                        
                        # LOGICA DE EXPORTACIÓN (Resumida para no hacer el código gigante, 
                        # usa la misma lógica de cálculo de horas del paso anterior)
                        # ... Aquí iría el bloque de cálculo de horas que ya tenías ...
                        # Para simplificar este ejemplo, exportamos los datos crudos, 
                        # pero puedes pegar aquí tu bloque de lógica anterior.
                        
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                             df_mes.to_excel(writer, sheet_name='Datos', index=False)
                             
                        buffer.seek(0)
                        st.download_button("📥 Descargar", buffer, f"Informe_{mes_seleccionado.replace('/','-')}.xlsx")
                else:
                    st.warning("Sin datos.")
            except Exception as e:
                st.error(f"Error cargando informes: {e}")

    elif password:
        st.error("Contraseña incorrecta")
