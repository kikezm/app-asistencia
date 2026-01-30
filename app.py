import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import os
import streamlit_javascript as st_js
import io
import uuid
import hashlib # <--- Librería para la seguridad criptográfica

# --- CLAVE SECRETA DE FIRMA ---
# Cambia esto por una frase que solo tú sepas. Es la "llave" de la validación.
SECRET_KEY = "MI_EMPRESA_2026_SEGURIDAD_TOTAL"

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
    try:
        sheet = client.open("Base de Datos Asistencia").worksheet(nombre_hoja)
        return sheet
    except gspread.WorksheetNotFound:
        st.error(f"❌ No encuentro la pestaña '{nombre_hoja}'.")
        st.stop()

# --- FUNCIONES DE SEGURIDAD (FIRMA DIGITAL) ---
def generar_firma(fecha, hora, nombre, tipo, dispositivo):
    """Crea un código único basado en los datos y la clave secreta"""
    # Concatenamos todo en una sola cadena de texto
    datos_brutos = f"{fecha}{hora}{nombre}{tipo}{dispositivo}{SECRET_KEY}"
    # Creamos el Hash SHA256 (imposible de falsificar manualmente)
    return hashlib.sha256(datos_brutos.encode()).hexdigest()

def verificar_integridad(row):
    """Comprueba si la fila es auténtica o ha sido manipulada"""
    try:
        firma_guardada = row.get('Firma', '')
        if not firma_guardada:
            return "❌ SIN FIRMA" # Registros antiguos o manuales
        
        # Recalculamos la firma con los datos que vemos
        firma_calculada = generar_firma(
            row['Fecha'], row['Hora'], row['Empleado'], 
            row['Tipo'], row['Dispositivo']
        )
        
        if firma_guardada == firma_calculada:
            return "✅ OK"
        else:
            return "⚠️ MANIPULADO" # Los datos no coinciden con la firma
    except:
        return "❓ ERROR"

# --- FUNCIONES AUXILIARES ---
def obtener_nombre_por_token(token):
    try:
        sheet_users = conectar_google_sheets("Usuarios")
        records = sheet_users.get_all_records()
        token_limpio = str(token).strip()
        for row in records:
            if str(row['ID']).strip() == token_limpio:
                return row['Nombre']
        return None
    except:
        return None

def registrar_fichaje(nombre, tipo, info_dispositivo):
    try:
        sheet = conectar_google_sheets("Hoja 1") 
        
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M:%S")
        
        # 1. Generamos la firma de seguridad antes de guardar
        firma_seguridad = generar_firma(fecha, hora, nombre, tipo, info_dispositivo)
        
        # 2. Guardamos la fila INCLUYENDO la firma en la Columna F
        sheet.append_row([fecha, hora, nombre, tipo, info_dispositivo, firma_seguridad])
        
        st.success(f"✅ {tipo} verificada y guardada para {nombre}")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error guardando datos: {e}")

# --- INTERFAZ ---
st.set_page_config(page_title="Control Asistencia", page_icon="🛡️")

try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

params = st.query_params
token_acceso = params.get("token", None)

st.title("🛡️ Control de Asistencia Verificado")

# ==========================================
# MODO EMPLEADO
# ==========================================
if token_acceso:
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
        st.error("⛔ ACCESO DENEGADO")

# ==========================================
# MODO ADMINISTRADOR
# ==========================================
else:
    st.sidebar.title("Administración")
    menu = ["Generar Usuarios", "Auditoría e Informes"]
    opcion = st.sidebar.radio("Ir a:", menu)
    
    password = st.sidebar.text_input("Contraseña Admin", type="password")
    
    if password == "admin123": 
        
        if opcion == "Generar Usuarios":
            # (El código de generar usuarios es igual al anterior)
            st.header("👥 Gestión de Empleados")
            with st.form("nuevo_empleado"):
                nuevo_nombre = st.text_input("Nombre Completo")
                submit = st.form_submit_button("Crear Empleado")
                if submit and nuevo_nombre:
                    try:
                        sheet_users = conectar_google_sheets("Usuarios")
                        nuevo_id = str(uuid.uuid4())
                        sheet_users.append_row([nuevo_id, nuevo_nombre])
                        # CAMBIA POR TU URL REAL
                        MI_URL_REAL = "https://app-asistencia-dknejmfedu4pswfrqf7prc.streamlit.app/" 
                        link = f"{MI_URL_REAL}/?token={nuevo_id}"
                        st.success(f"Usuario {nuevo_nombre} creado.")
                        st.code(link, language="text")
                    except Exception as e:
                        st.error(f"Error: {e}")

        elif opcion == "Auditoría e Informes":
            st.header("🕵️ Auditoría de Seguridad")
            
            try:
                sheet = conectar_google_sheets("Hoja 1")
                datos = sheet.get_all_records()
                
                if datos:
                    df = pd.DataFrame(datos)
                    
                    # --- VALIDACIÓN DE SEGURIDAD ---
                    # Aplicamos la función verificadora a cada fila
                    df['Estado'] = df.apply(verificar_integridad, axis=1)
                    
                    # Reordenamos columnas para poner el Estado al principio
                    cols = ['Estado', 'Fecha', 'Hora', 'Empleado', 'Tipo', 'Dispositivo', 'Firma']
                    # Aseguramos que existan todas las columnas
                    for col in cols:
                        if col not in df.columns:
                            df[col] = ""
                    df = df[cols]
                    
                    # Procesamiento fechas para filtros
                    df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                    df = df.sort_values(by='FechaHora', ascending=False)
                    
                    # Métrica de seguridad
                    manipulados = len(df[df['Estado'] == "⚠️ MANIPULADO"])
                    if manipulados > 0:
                        st.error(f"🚨 ATENCIÓN: Se han detectado {manipulados} registros manipulados manualmente.")
                    else:
                        st.success("✅ Todos los registros son auténticos.")

                    # Visualización
                    st.dataframe(df.drop(columns=['Firma']), use_container_width=True) # Ocultamos la firma larga porque es fea visualmente
                    
                    # (Aquí iría el resto de lógica de descarga de Excel...)
                    # Si quieres descargar, descarga el DF que ya incluye la columna "Estado"
                    
                else:
                    st.warning("Sin datos.")
            except Exception as e:
                st.error(f"Error: {e}")

    elif password:
        st.error("Contraseña incorrecta")
