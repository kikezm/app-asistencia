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

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Control Asistencia", page_icon="🛡️")

# --- CARGA DE SECRETOS ---
try:
    SECRET_KEY = st.secrets["general"]["secret_key"]
    ADMIN_PASSWORD = st.secrets["general"]["admin_password"]
    SHEET_NAME = st.secrets["general"]["sheet_name"]
    APP_URL = st.secrets["general"]["app_url"]
except Exception as e:
    st.error("⚠️ Error Crítico: Faltan secretos de configuración.")
    st.stop()

# --- CONEXIÓN A GOOGLE SHEETS ---
def conectar_google_sheets(nombre_hoja_especifica):
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
        sheet = client.open(SHEET_NAME).worksheet(nombre_hoja_especifica)
        return sheet
    except gspread.WorksheetNotFound:
        st.error(f"❌ No encuentro la pestaña '{nombre_hoja_especifica}'. Créala en Google Sheets.")
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
            if str(row['ID']).strip() == token_limpio: return row['Nombre']
        return None
    except: return None

def obtener_estado_actual(nombre_empleado):
    try:
        sheet = conectar_google_sheets("Hoja 1")
        data = sheet.get_all_records()
        if not data: return "FUERA"
        df = pd.DataFrame(data)
        df_emp = df[df['Empleado'] == nombre_empleado]
        if df_emp.empty: return "FUERA"
        df_emp['FechaHora'] = pd.to_datetime(df_emp['Fecha'] + ' ' + df_emp['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        df_emp = df_emp.sort_values(by='FechaHora')
        return "DENTRO" if df_emp.iloc[-1]['Tipo'] == "ENTRADA" else "FUERA"
    except: return "DESCONOCIDO"

# --- NUEVA FUNCIÓN: VERIFICAR CALENDARIO ---
def puede_fichar_hoy(nombre_empleado):
    """Devuelve (True, "") si puede fichar o (False, "Motivo") si está bloqueado"""
    try:
        sheet_cal = conectar_google_sheets("Calendario")
        registros = sheet_cal.get_all_records()
        
        hoy = datetime.now().strftime("%d/%m/%Y")
        
        for row in registros:
            # Si la fecha coincide con HOY
            if row['Fecha'] == hoy:
                # CASO 1: Es un festivo GLOBAL
                if row['Tipo'] == "GLOBAL":
                    return False, f"Festivo: {row['Motivo']}"
                
                # CASO 2: Es vacaciones de ESTE EMPLEADO
                if row['Tipo'] == "INDIVIDUAL" and row['Empleado'] == nombre_empleado:
                    return False, f"Vacaciones asignadas: {row['Motivo']}"
        
        return True, "OK"
    except Exception as e:
        # Si falla la lectura (ej: pestaña vacía), permitimos fichar por seguridad
        return True, "OK"

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
try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

params = st.query_params
token_acceso = params.get("token", None)

st.title("🛡️ Control de Asistencia")

# ==========================================
# MODO EMPLEADO
# ==========================================
if token_acceso:
    nombre_usuario = obtener_nombre_por_token(token_acceso)
    
    if nombre_usuario:
        st.info(f"👋 Hola, **{nombre_usuario}**")
        
        # 1. VERIFICAMOS EL CALENDARIO PRIMERO
        puede_trabajar, motivo = puede_fichar_hoy(nombre_usuario)
        
        if not puede_trabajar:
            # PANTALLA DE BLOQUEO POR VACACIONES/FESTIVO
            st.error(f"⛔ NO PUEDES FICHAR HOY")
            st.warning(f"Motivo: **{motivo}**")
            st.caption("Si crees que es un error, contacta con administración.")
        
        else:
            # SI PUEDE TRABAJAR, MOSTRAMOS LOS BOTONES
            estado_actual = obtener_estado_actual(nombre_usuario)
            st.write("---")
            
            if estado_actual == "FUERA":
                st.markdown("### 🏠 Estás FUERA. ¿Quieres entrar?")
                if st.button("🟢 REGISTRAR ENTRADA", use_container_width=True):
                    registrar_fichaje(nombre_usuario, "ENTRADA", ua_string)
            elif estado_actual == "DENTRO":
                st.markdown("### 🏭 Estás DENTRO. ¿Quieres salir?")
                if st.button("🔴 REGISTRAR SALIDA", use_container_width=True):
                    registrar_fichaje(nombre_usuario, "SALIDA", ua_string)
            else:
                c1, c2 = st.columns(2)
                with c1: 
                    if st.button("🟢 ENTRADA"): registrar_fichaje(nombre_usuario, "ENTRADA", ua_string)
                with c2: 
                    if st.button("🔴 SALIDA"): registrar_fichaje(nombre_usuario, "SALIDA", ua_string)
    else:
        st.error("⛔ ACCESO DENEGADO")

# ==========================================
# MODO ADMINISTRADOR
# ==========================================
else:
    st.sidebar.title("Administración")
    menu = ["Generar Usuarios", "Calendario y Festivos", "Auditoría e Informes"]
    opcion = st.sidebar.radio("Ir a:", menu)
    
    password = st.sidebar.text_input("Contraseña Admin", type="password")
    
    if password == ADMIN_PASSWORD:
        
        # --- SECCIÓN: CALENDARIO ---
        if opcion == "Calendario y Festivos":
            st.header("📅 Gestión de Festivos y Vacaciones")
            st.info("Añade días donde NO se permite fichar.")
            
            with st.form("nuevo_festivo"):
                col_cal1, col_cal2 = st.columns(2)
                with col_cal1:
                    fecha_selec = st.date_input("Selecciona fecha")
                    # Formateamos la fecha a String DD/MM/AAAA para guardarla
                    fecha_str = fecha_selec.strftime("%d/%m/%Y")
                with col_cal2:
                    tipo_bloqueo = st.selectbox("Tipo de Bloqueo", ["GLOBAL (Toda la empresa)", "INDIVIDUAL (Un empleado)"])
                
                nombre_emp_cal = "TODOS"
                if tipo_bloqueo == "INDIVIDUAL (Un empleado)":
                    # Recuperamos lista de empleados para el desplegable
                    try:
                        sh_u = conectar_google_sheets("Usuarios")
                        lista_nombres = [r['Nombre'] for r in sh_u.get_all_records()]
                        nombre_emp_cal = st.selectbox("Empleado:", lista_nombres)
                    except:
                        st.error("No se pudo cargar la lista de empleados.")
                
                motivo = st.text_input("Motivo (Ej: Navidad, Vacaciones de Verano)")
                
                submit_cal = st.form_submit_button("📅 Guardar Fecha Bloqueada")
                
                if submit_cal and motivo:
                    try:
                        sheet_cal = conectar_google_sheets("Calendario")
                        sheet_cal.append_row([fecha_str, "GLOBAL" if tipo_bloqueo.startswith("GLOBAL") else "INDIVIDUAL", nombre_emp_cal, motivo])
                        st.success(f"Bloqueo guardado para el {fecha_str}")
                    except Exception as e:
                        st.error(f"Error guardando: {e}")

            st.write("---")
            st.write("### 🗓️ Días Bloqueados Actualmente")
            try:
                sheet_cal = conectar_google_sheets("Calendario")
                df_cal = pd.DataFrame(sheet_cal.get_all_records())
                if not df_cal.empty:
                    st.dataframe(df_cal)
                else:
                    st.info("No hay fechas bloqueadas.")
            except:
                st.warning("No se pudo leer el calendario.")

        # --- SECCIÓN: GENERAR USUARIOS (Igual que antes) ---
        elif opcion == "Generar Usuarios":
            st.header("👥 Gestión de Empleados")
            with st.form("nuevo_empleado"):
                nuevo_nombre = st.text_input("Nombre Completo")
                submit = st.form_submit_button("Crear Empleado")
                if submit and nuevo_nombre:
                    try:
                        sheet_users = conectar_google_sheets("Usuarios")
                        nuevo_id = str(uuid.uuid4())
                        sheet_users.append_row([nuevo_id, nuevo_nombre])
                        link = f"{APP_URL}/?token={nuevo_id}"
                        st.success(f"Usuario {nuevo_nombre} creado.")
                        st.code(link, language="text")
                    except Exception as e:
                        st.error(f"Error: {e}")

        # --- SECCIÓN: AUDITORÍA (Igual que antes) ---
        elif opcion == "Auditoría e Informes":
            st.header("🕵️ Auditoría y Control")
            try:
                sheet = conectar_google_sheets("Hoja 1")
                datos = sheet.get_all_records()
                if datos:
                    df = pd.DataFrame(datos)
                    df['Estado'] = df.apply(verificar_integridad, axis=1)
                    df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                    df = df.sort_values(by='FechaHora', ascending=False)
                    df['Mes_Año'] = df['FechaHora'].dt.strftime('%m/%Y')
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        lista_meses = ["Todos"] + sorted(df['Mes_Año'].unique().tolist(), reverse=True)
                        filtro_mes = st.selectbox("Mes:", lista_meses)
                    with c2:
                        emps = df[df['Mes_Año'] == filtro_mes]['Empleado'].unique() if filtro_mes != "Todos" else df['Empleado'].unique()
                        filtro_emp = st.selectbox("Empleado:", ["Todos"] + sorted(list(emps)))
                    
                    df_final = df.copy()
                    if filtro_mes != "Todos": df_final = df_final[df_final['Mes_Año'] == filtro_mes]
                    if filtro_emp != "Todos": df_final = df_final[df_final['Empleado'] == filtro_emp]
                    
                    # Cálculo horas
                    tot_seg = 0
                    for emp in df_final['Empleado'].unique():
                        sub_df = df_final[df_final['Empleado'] == emp].sort_values(by='FechaHora')
                        ent_t = None
                        for _, r in sub_df.iterrows():
                            if r['Tipo'] == 'ENTRADA': ent_t = r['FechaHora']
                            elif r['Tipo'] == 'SALIDA' and ent_t:
                                tot_seg += (r['FechaHora'] - ent_t).total_seconds()
                                ent_t = None
                    ht = int(tot_seg // 3600)
                    mt = int((tot_seg % 3600) // 60)
                    
                    st.metric("Horas Trabajadas (Selección)", f"{ht}h {mt}m")
                    
                    ord_v = ['Fecha', 'Hora', 'Empleado', 'Tipo', 'Estado', 'Dispositivo']
                    for c in ord_v: 
                        if c not in df_final.columns: df_final[c]=""
                    st.dataframe(df_final.reindex(columns=ord_v), use_container_width=True)
                    
                    # Descarga
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_final.reindex(columns=ord_v).to_excel(writer, sheet_name='Reporte', index=False)
                        df_final.to_excel(writer, sheet_name='Datos_Completos', index=False)
                    buffer.seek(0)
                    st.download_button("📥 Descargar Excel", buffer, f"Reporte.xlsx")
                else: st.warning("Sin datos.")
            except Exception as e: st.error(f"Error: {e}")

    elif password:
        st.error("Contraseña incorrecta")


