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
        # Intenta abrir la hoja específica
        sheet = client.open("Base de Datos Asistencia").worksheet(nombre_hoja)
        return sheet
    except gspread.WorksheetNotFound:
        # Si falla, avisa
        st.error(f"❌ No encuentro la pestaña '{nombre_hoja}'. Verifica el nombre en Google Sheets.")
        st.stop()

# --- FUNCIONES AUXILIARES ---
def obtener_nombre_por_token(token):
    try:
        sheet_users = conectar_google_sheets("Usuarios")
        records = sheet_users.get_all_records()
        for row in records:
            if str(row['ID']).strip() == str(token).strip():
                return row['Nombre']
        return None
    except:
        return None

def registrar_fichaje(nombre, tipo, info_dispositivo):
    try:
        # CAMBIA "Hoja 1" SI TU PESTAÑA DE DATOS SE LLAMA DISTINTO
        sheet = conectar_google_sheets("Hoja 1") 
        
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M:%S")
        
        sheet.append_row([fecha, hora, nombre, tipo, info_dispositivo])
        
        st.success(f"✅ {tipo} registrada correctamente para {nombre}")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error guardando datos: {e}")

# --- INTERFAZ ---
st.set_page_config(page_title="Control Asistencia", page_icon="🔒")

# Detectar dispositivo
try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

# Detectar Token URL
params = st.query_params
token_acceso = params.get("token", None)

st.title("🔒 Control de Asistencia")

# ==========================================
# MODO EMPLEADO (ACCESO CON TOKEN)
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
        st.error("⛔ Token no válido o usuario no encontrado.")

# ==========================================
# MODO ADMINISTRADOR (LOGIN)
# ==========================================
else:
    st.sidebar.title("Administración")
    menu = ["Generar Usuarios", "Informes y Nóminas"]
    opcion = st.sidebar.radio("Ir a:", menu)
    
    password = st.sidebar.text_input("Contraseña Admin", type="password")
    
    if password == "admin123": # <--- TU CONTRASEÑA
        
        # --- SECCIÓN: CREAR USUARIOS ---
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
                        
                        # CAMBIA ESTO POR TU URL REAL (COPIALA DEL NAVEGADOR)
                        MI_URL_REAL = "https://tu-app-asistencia.streamlit.app"
                        link = f"{MI_URL_REAL}/?token={nuevo_id}"
                        
                        st.success(f"Usuario {nuevo_nombre} creado.")
                        st.code(link, language="text")
                    except Exception as e:
                        st.error(f"Error: {e}")

            st.write("---")
            st.write("### 📋 Usuarios Activos")
            try:
                sheet_u = conectar_google_sheets("Usuarios")
                df_u = pd.DataFrame(sheet_u.get_all_records())
                st.dataframe(df_u)
            except:
                st.info("No hay usuarios.")

        # --- SECCIÓN: INFORMES (CON PREVISUALIZACIÓN) ---
        elif opcion == "Informes y Nóminas":
            st.header("📊 Informes Mensuales")
            
            try:
                sheet = conectar_google_sheets("Hoja 1") # Hoja de datos
                datos = sheet.get_all_records()
                
                if datos:
                    df = pd.DataFrame(datos)
                    # Convertir fechas
                    df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S')
                    df = df.sort_values(by='FechaHora')
                    df['Mes_Año'] = df['FechaHora'].dt.strftime('%m/%Y')
                    
                    # Filtros
                    col1, col2 = st.columns(2)
                    with col1:
                        lista_meses = sorted(df['Mes_Año'].unique().tolist(), reverse=True)
                        mes_seleccionado = st.selectbox("Selecciona Mes:", lista_meses)
                    
                    # Filtrar DF por mes
                    df_mes = df[df['Mes_Año'] == mes_seleccionado].copy()
                    
                    with col2:
                        lista_empleados = ["TODOS (Resumen Global)"] + list(df_mes['Empleado'].unique())
                        empleado_selec = st.selectbox("Selecciona Empleado:", lista_empleados)
                    
                    st.write("---")
                    
                    # --- CÁLCULOS Y PREVISUALIZACIÓN ---
                    buffer = io.BytesIO()
                    
                    # CASO A: TODOS LOS EMPLEADOS
                    if empleado_selec == "TODOS (Resumen Global)":
                        resumen_global = []
                        for emp in df_mes['Empleado'].unique():
                            df_emp = df_mes[df_mes['Empleado'] == emp].sort_values(by='FechaHora')
                            segundos = 0
                            entrada_pend = None
                            for _, row in df_emp.iterrows():
                                if row['Tipo'] == 'ENTRADA':
                                    entrada_pend = row['FechaHora']
                                elif row['Tipo'] == 'SALIDA' and entrada_pend:
                                    segundos += (row['FechaHora'] - entrada_pend).total_seconds()
                                    entrada_pend = None
                            
                            h = int(segundos // 3600)
                            m = int((segundos % 3600) // 60)
                            resumen_global.append({"Empleado": emp, "Horas Totales": f"{h}h {m}m"})
                        
                        df_preview = pd.DataFrame(resumen_global)
                        
                        st.subheader(f"Vista Previa: {mes_seleccionado}")
                        st.dataframe(df_preview, use_container_width=True) # <--- AQUÍ ESTÁ LA PREVISUALIZACIÓN
                        
                        # Preparar Excel
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df_preview.to_excel(writer, sheet_name='Resumen', index=False)
                            df_mes.to_excel(writer, sheet_name='Datos Crudos', index=False)
                            
                        nombre_archivo = f"Global_{mes_seleccionado.replace('/','-')}.xlsx"

                    # CASO B: UN EMPLEADO
                    else:
                        df_emp = df_mes[df_mes['Empleado'] == empleado_selec].sort_values(by='FechaHora')
                        resumen_dias = []
                        total_seg_mes = 0
                        dias = df_emp['Fecha'].unique()
                        
                        for dia in dias:
                            movs = df_emp[df_emp['Fecha'] == dia]
                            seg_dia = 0
                            ent_pend = None
                            for _, row in movs.iterrows():
                                if row['Tipo'] == 'ENTRADA':
                                    ent_pend = row['FechaHora']
                                elif row['Tipo'] == 'SALIDA' and ent_pend:
                                    seg_dia += (row['FechaHora'] - ent_pend).total_seconds()
                                    ent_pend = None
                            
                            h_dia = int(seg_dia // 3600)
                            m_dia = int((seg_dia % 3600) // 60)
                            total_seg_mes += seg_dia
                            resumen_dias.append({"Fecha": dia, "Horas": f"{h_dia}h {m_dia}m"})
                        
                        df_preview = pd.DataFrame(resumen_dias)
                        
                        # Mostrar Totales
                        th = int(total_seg_mes // 3600)
                        tm = int((total_seg_mes % 3600) // 60)
                        st.info(f"Total acumulado: **{th}h {tm}m**")
                        
                        st.subheader(f"Detalle Diario: {empleado_selec}")
                        st.dataframe(df_preview, use_container_width=True) # <--- AQUÍ ESTÁ LA PREVISUALIZACIÓN
                        
                        # Preparar Excel
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df_preview.to_excel(writer, sheet_name='Resumen Diario', index=False)
                            df_emp.to_excel(writer, sheet_name='Fichajes', index=False)
                            
                        nombre_archivo = f"Nómina_{empleado_selec}_{mes_seleccionado.replace('/','-')}.xlsx"

                    # BOTÓN DE DESCARGA
                    buffer.seek(0)
                    st.download_button(
                        label="📥 Descargar Excel",
                        data=buffer,
                        file_name=nombre_archivo,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                else:
                    st.warning("No hay datos registrados aún.")
            except Exception as e:
                st.error(f"Error cargando informes: {e}")

    elif password:
        st.error("Contraseña incorrecta")
