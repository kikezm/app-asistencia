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
import hashlib

# --- CLAVE SECRETA DE FIRMA ---
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

# --- FUNCIONES DE LÓGICA ---
def generar_firma(fecha, hora, nombre, tipo, dispositivo):
    datos_brutos = f"{fecha}{hora}{nombre}{tipo}{dispositivo}{SECRET_KEY}"
    return hashlib.sha256(datos_brutos.encode()).hexdigest()

def verificar_integridad(row):
    try:
        firma_guardada = row.get('Firma', '')
        if not firma_guardada: return "❌ SIN FIRMA"
        firma_calculada = generar_firma(row['Fecha'], row['Hora'], row['Empleado'], row['Tipo'], row['Dispositivo'])
        return "✅ OK" if firma_guardada == firma_calculada else "⚠️ MANIPULADO"
    except: return "❓ ERROR"

def obtener_nombre_por_token(token):
    try:
        sheet_users = conectar_google_sheets("Usuarios")
        records = sheet_users.get_all_records()
        token_limpio = str(token).strip()
        for row in records:
            if str(row['ID']).strip() == token_limpio:
                return row['Nombre']
        return None
    except: return None

# --- NUEVA FUNCIÓN: DETECTAR SI ESTÁ DENTRO O FUERA ---
def obtener_estado_actual(nombre_empleado):
    try:
        sheet = conectar_google_sheets("Hoja 1")
        # Obtenemos todos los registros
        data = sheet.get_all_records()
        
        if not data:
            return "FUERA" # Si no hay datos, está fuera
            
        df = pd.DataFrame(data)
        
        # Filtramos solo los movimientos de este empleado
        df_emp = df[df['Empleado'] == nombre_empleado]
        
        if df_emp.empty:
            return "FUERA" # Si nunca ha fichado, está fuera
            
        # Ordenamos por fecha y hora para ver el ÚLTIMO movimiento real
        # Aseguramos que Fecha y Hora sean interpretables
        df_emp['FechaHora'] = pd.to_datetime(df_emp['Fecha'] + ' ' + df_emp['Hora'], format='%d/%m/%Y %H:%M:%S')
        df_emp = df_emp.sort_values(by='FechaHora')
        
        # Cogemos el último registro
        ultimo_tipo = df_emp.iloc[-1]['Tipo']
        
        if ultimo_tipo == "ENTRADA":
            return "DENTRO"
        else:
            return "FUERA"
            
    except Exception as e:
        # En caso de error de conexión, por seguridad asumimos que no sabemos (o dejamos fichar ambos)
        return "DESCONOCIDO"

def registrar_fichaje(nombre, tipo, info_dispositivo):
    try:
        sheet = conectar_google_sheets("Hoja 1") 
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M:%S")
        firma = generar_firma(fecha, hora, nombre, tipo, info_dispositivo)
        sheet.append_row([fecha, hora, nombre, tipo, info_dispositivo, firma])
        
        st.success(f"✅ {tipo} registrada correctamente.")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error: {e}")

# --- INTERFAZ ---
st.set_page_config(page_title="Control Asistencia", page_icon="🛡️")

try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

params = st.query_params
token_acceso = params.get("token", None)

st.title("🛡️ Control de Asistencia")

# ==========================================
# MODO EMPLEADO INTELIGENTE
# ==========================================
if token_acceso:
    nombre_usuario = obtener_nombre_por_token(token_acceso)
    
    if nombre_usuario:
        st.info(f"👋 Hola, **{nombre_usuario}**")
        
        # 1. CONSULTAMOS EL ESTADO ACTUAL
        estado_actual = obtener_estado_actual(nombre_usuario)
        
        st.write("---")
        
        # 2. MOSTRAMOS SOLO EL BOTÓN LÓGICO
        if estado_actual == "FUERA":
            st.markdown("### 🏠 Estás FUERA. ¿Quieres entrar?")
            if st.button("🟢 REGISTRAR ENTRADA", use_container_width=True):
                registrar_fichaje(nombre_usuario, "ENTRADA", ua_string)
                
        elif estado_actual == "DENTRO":
            st.markdown("### 🏭 Estás DENTRO. ¿Quieres salir?")
            if st.button("🔴 REGISTRAR SALIDA", use_container_width=True):
                registrar_fichaje(nombre_usuario, "SALIDA", ua_string)
        
        else:
            # Si falla la lectura (raro), mostramos ambos por seguridad
            st.warning("No pude verificar tu estado anterior. Elige manualmente:")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🟢 ENTRADA", use_container_width=True): registrar_fichaje(nombre_usuario, "ENTRADA", ua_string)
            with col2:
                if st.button("🔴 SALIDA", use_container_width=True): registrar_fichaje(nombre_usuario, "SALIDA", ua_string)

    else:
        st.error("⛔ ACCESO DENEGADO")

# ==========================================
# MODO ADMINISTRADOR (Sin Cambios)
# ==========================================
else:
    st.sidebar.title("Administración")
    menu = ["Generar Usuarios", "Auditoría e Informes"]
    opcion = st.sidebar.radio("Ir a:", menu)
    
    password = st.sidebar.text_input("Contraseña Admin", type="password")
    
    if password == "admin123": 
        if opcion == "Generar Usuarios":
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
                    st.header("🕵️ Auditoría y Control")
                    
                    try:
                        sheet = conectar_google_sheets("Hoja 1")
                        datos = sheet.get_all_records()
                        
                        if datos:
                            df = pd.DataFrame(datos)
                            
                            # 1. CÁLCULOS PREVIOS (Seguridad y Fechas)
                            # Calculamos si el fichaje es válido o manipulado
                            df['Estado'] = df.apply(verificar_integridad, axis=1)
                            
                            # Preparamos fechas para poder filtrar y ordenar
                            df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                            df = df.sort_values(by='FechaHora', ascending=False)
                            df['Mes_Año'] = df['FechaHora'].dt.strftime('%m/%Y') # Columna auxiliar para el filtro
                            
                            st.write("---")
                            
                            # 2. ZONA DE FILTROS (¡Recuperada!)
                            col_filtros1, col_filtros2 = st.columns(2)
                            
                            with col_filtros1:
                                # Filtro de Mes
                                lista_meses = ["Todos"] + sorted(df['Mes_Año'].unique().tolist(), reverse=True)
                                filtro_mes = st.selectbox("Filtrar por Mes:", lista_meses)
                            
                            with col_filtros2:
                                # Filtro de Empleado
                                # Si hemos filtrado mes, solo mostramos empleados de ese mes
                                if filtro_mes != "Todos":
                                    empleados_disponibles = df[df['Mes_Año'] == filtro_mes]['Empleado'].unique()
                                else:
                                    empleados_disponibles = df['Empleado'].unique()
                                    
                                lista_empleados = ["Todos"] + sorted(list(empleados_disponibles))
                                filtro_empleado = st.selectbox("Filtrar por Empleado:", lista_empleados)

                            # 3. APLICAMOS LOS FILTROS
                            df_final = df.copy()
                            
                            if filtro_mes != "Todos":
                                df_final = df_final[df_final['Mes_Año'] == filtro_mes]
                            
                            if filtro_empleado != "Todos":
                                df_final = df_final[df_final['Empleado'] == filtro_empleado]

                            # 4. ORDEN VISUAL DE COLUMNAS (Lo que pediste antes)
                            orden_visual = ['Fecha', 'Hora', 'Empleado', 'Tipo', 'Estado', 'Dispositivo']
                            # Aseguramos que existan las columnas por si acaso
                            for col in orden_visual:
                                if col not in df_final.columns: df_final[col] = ""
                            
                            df_visual = df_final.reindex(columns=orden_visual)

                            # 5. MÉTRICAS Y VISUALIZACIÓN
                            # Contamos manipulados solo de lo que estamos viendo (filtrado)
                            manipulados = len(df_final[df_final['Estado'] == "⚠️ MANIPULADO"])
                            total_registros = len(df_final)
                            
                            col_metric1, col_metric2 = st.columns(2)
                            col_metric1.metric("Registros Encontrados", total_registros)
                            if manipulados > 0:
                                col_metric2.error(f"🚨 {manipulados} Manipulados")
                            else:
                                col_metric2.success("✅ Integridad 100%")

                            # Tabla principal
                            st.dataframe(df_visual, use_container_width=True)
                            
                            # 6. DESCARGA EXCEL
                            # Descargamos exactamente lo que se ve filtrado
                            buffer = io.BytesIO()
                            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                # Hoja principal limpia
                                df_visual.to_excel(writer, sheet_name='Reporte', index=False)
                                # Hoja con datos técnicos (Firma, etc) por si hace falta
                                df_final.to_excel(writer, sheet_name='Datos_Completos', index=False)
                                
                            buffer.seek(0)
                            nombre_archivo = f"Reporte_{filtro_empleado}_{filtro_mes.replace('/','-')}.xlsx"
                            
                            st.download_button(
                                label="📥 Descargar Selección en Excel",
                                data=buffer,
                                file_name=nombre_archivo,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                            
                        else:
                            st.warning("La base de datos está vacía.")
                    except Exception as e:
                        st.error(f"Error en auditoría: {e}")

