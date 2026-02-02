import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time
import os
import streamlit_javascript as st_js
import io
import uuid
import hashlib
from streamlit_calendar import calendar # IMPORTACIÓN VITAL

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

# --- CONEXIÓN BASE A GOOGLE SHEETS ---
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
    except:
        return None

# --- FUNCIONES DE LECTURA CON CACHÉ INTELIGENTE ---
# Usamos TTL para no saturar la API, pero permitimos borrar la caché cuando guardamos datos.

@st.cache_data(ttl=600)
def cargar_datos_usuarios():
    sheet = conectar_google_sheets("Usuarios")
    if sheet: return sheet.get_all_records()
    return []

@st.cache_data(ttl=600)
def cargar_datos_calendario():
    sheet = conectar_google_sheets("Calendario")
    if sheet: return sheet.get_all_records()
    return []

@st.cache_data(ttl=60)
def cargar_datos_registros():
    sheet = conectar_google_sheets("Hoja 1")
    if sheet: return sheet.get_all_records()
    return []

# --- FUNCIONES LÓGICAS ---
def generar_firma(fecha, hora, nombre, tipo, dispositivo):
    datos = f"{fecha}{hora}{nombre}{tipo}{dispositivo}{SECRET_KEY}"
    return hashlib.sha256(datos.encode()).hexdigest()

def verificar_integridad(row):
    try:
        firma = row.get('Firma', '')
        if not firma: return "❌ SIN FIRMA"
        calc = generar_firma(row['Fecha'], row['Hora'], row['Empleado'], row['Tipo'], row['Dispositivo'])
        return "✅ OK" if firma == calc else "⚠️ MANIPULADO"
    except: return "❓ ERROR"

def obtener_nombre_por_token(token):
    records = cargar_datos_usuarios()
    token_s = str(token).strip()
    for r in records:
        if str(r.get('ID')).strip() == token_s: return r.get('Nombre')
    return None

def obtener_estado_actual(nombre):
    data = cargar_datos_registros()
    if not data: return "FUERA"
    df = pd.DataFrame(data)
    if 'Empleado' not in df.columns: return "FUERA"
    df_emp = df[df['Empleado'] == nombre]
    if df_emp.empty: return "FUERA"
    
    # Ordenar por fecha real
    df_emp['DT'] = pd.to_datetime(df_emp['Fecha'] + ' ' + df_emp['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    df_emp = df_emp.sort_values(by='DT')
    
    return "DENTRO" if df_emp.iloc[-1]['Tipo'] == "ENTRADA" else "FUERA"

def puede_fichar_hoy(nombre):
    data = cargar_datos_calendario()
    hoy = datetime.now().strftime("%d/%m/%Y")
    for r in data:
        if r.get('Fecha') == hoy:
            if r.get('Tipo') == "GLOBAL": return False, f"Festivo: {r.get('Motivo')}"
            if r.get('Tipo') == "INDIVIDUAL" and r.get('Empleado') == nombre: return False, f"Vacaciones: {r.get('Motivo')}"
    return True, "OK"

def registrar_fichaje(nombre, tipo, disp):
    try:
        sheet = conectar_google_sheets("Hoja 1")
        if not sheet: st.error("Error conectando a Hoja 1"); return

        ahora = datetime.now()
        f, h = ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S")
        firma = generar_firma(f, h, nombre, tipo, disp)
        
        sheet.append_row([f, h, nombre, tipo, disp, firma])
        
        # IMPORTANTE: Limpiar caché para ver el cambio inmediato
        st.cache_data.clear()
        
        st.success(f"✅ {tipo} registrada correctamente.")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- INTERFAZ ---
try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

params = st.query_params
token_acceso = params.get("token", None)

st.title("🛡️ Control de Asistencia")

# ==========================================
# VISTA EMPLEADO
# ==========================================
if token_acceso:
    nombre = obtener_nombre_por_token(token_acceso)
    
    if nombre:
        st.info(f"👋 Hola, **{nombre}**")
        ok, motivo = puede_fichar_hoy(nombre)
        
        if not ok:
            st.error("⛔ NO PUEDES FICHAR HOY")
            st.warning(f"Motivo: **{motivo}**")
        else:
            estado = obtener_estado_actual(nombre)
            st.write("---")
            if estado == "FUERA":
                st.markdown("### 🏠 Estás FUERA. ¿Entrar?")
                if st.button("🟢 ENTRADA", use_container_width=True): registrar_fichaje(nombre, "ENTRADA", ua_string)
            elif estado == "DENTRO":
                st.markdown("### 🏭 Estás DENTRO. ¿Salir?")
                if st.button("🔴 SALIDA", use_container_width=True): registrar_fichaje(nombre, "SALIDA", ua_string)
            else:
                c1,c2 = st.columns(2)
                with c1: 
                    if st.button("🟢 ENTRADA"): registrar_fichaje(nombre, "ENTRADA", ua_string)
                with c2: 
                    if st.button("🔴 SALIDA"): registrar_fichaje(nombre, "SALIDA", ua_string)
    else:
        st.error("⛔ Token inválido o expirado.")

# ==========================================
# VISTA ADMIN
# ==========================================
else:
    st.sidebar.title("Administración")
    menu = ["Generar Usuarios", "Calendario y Festivos", "Auditoría e Informes"]
    opcion = st.sidebar.radio("Ir a:", menu)
    pwd = st.sidebar.text_input("Contraseña", type="password")
    
    if pwd == ADMIN_PASSWORD:
        
        # --- 1. USUARIOS ---
        if opcion == "Generar Usuarios":
            st.header("👥 Gestión de Empleados")
            with st.form("new_user"):
                n_nombre = st.text_input("Nombre Completo")
                if st.form_submit_button("Crear Empleado"):
                    sheet = conectar_google_sheets("Usuarios")
                    uid = str(uuid.uuid4())
                    sheet.append_row([uid, n_nombre])
                    st.cache_data.clear() # Limpiar caché para que aparezca en listas
                    st.success(f"Creado: {n_nombre}")
                    st.code(f"{APP_URL}/?token={uid}")
        
        # --- 2. CALENDARIO ---
        elif opcion == "Calendario y Festivos":
            st.header("📅 Calendario Laboral")
            t_gest, t_vis = st.tabs(["✍️ Gestión", "👀 Visualizar"])
            
            with t_gest:
                st.info("Añadir días festivos o vacaciones.")
                with st.form("add_cal"):
                    c1, c2 = st.columns(2)
                    d_ini = c1.date_input("Inicio", format="DD/MM/YYYY")
                    d_fin = c2.date_input("Fin", value=d_ini, format="DD/MM/YYYY")
                    
                    st.write("---")
                    c3, c4 = st.columns(2)
                    tipo = c3.selectbox("Tipo", ["INDIVIDUAL (Un empleado)", "GLOBAL (Empresa)"])
                    
                    nom_emp = "TODOS"
                    if "INDIVIDUAL" in tipo:
                        usrs = cargar_datos_usuarios()
                        l_n = [u['Nombre'] for u in usrs] if usrs else []
                        nom_emp = c3.selectbox("Empleado:", l_n)
                    
                    modo = c4.radio("Días:", ["Todos", "Solo Fines de Semana"])
                    motivo = st.text_input("Motivo")
                    
                    if st.form_submit_button("💾 Guardar"):
                        sheet = conectar_google_sheets("Calendario")
                        rows = []
                        t_s = "GLOBAL" if "GLOBAL" in tipo else "INDIVIDUAL"
                        delta = d_fin - d_ini
                        for i in range(delta.days + 1):
                            dia = d_ini + timedelta(days=i)
                            if modo == "Solo Fines de Semana" and dia.weekday() < 5: continue
                            rows.append([dia.strftime("%d/%m/%Y"), t_s, nom_emp, motivo])
                        
                        if rows:
                            sheet.append_rows(rows)
                            st.cache_data.clear() # VITAL: Limpiar caché
                            st.success(f"Añadidos {len(rows)} días.")
                            time.sleep(1)
                            st.rerun()

                with st.expander("📂 Ver Tabla Completa"):
                    data = cargar_datos_calendario()
                    if data:
                        df = pd.DataFrame(data)
                        # Ordenar para edición
                        df['Aux'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
                        df = df.sort_values(by='Aux')
                        df_edit = df.drop(columns=['Aux'])
                        
                        ed = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True, hide_index=True)
                        
                        if st.button("💾 Guardar Cambios Tabla"):
                            # Reordenar antes de subir
                            df_final = ed.copy()
                            df_final['Aux'] = pd.to_datetime(df_final['Fecha'], format='%d/%m/%Y', errors='coerce')
                            df_final = df_final.dropna(subset=['Aux']).sort_values(by='Aux').drop(columns=['Aux'])
                            
                            vals = [df_final.columns.values.tolist()] + df_final.values.tolist()
                            sheet = conectar_google_sheets("Calendario")
                            sheet.clear()
                            sheet.update(vals)
                            st.cache_data.clear()
                            st.success("Tabla actualizada.")
                            time.sleep(1)
                            st.rerun()

            with t_vis:
                # LÓGICA DEL CALENDARIO (SIN CACHÉ VISUAL PARA EVITAR ERRORES)
                raw_cal = cargar_datos_calendario()
                
                if raw_cal:
                    df_c = pd.DataFrame(raw_cal)
                    
                    # Filtros
                    if 'Empleado' not in df_c.columns: df_c['Empleado'] = ""
                    if 'Tipo' not in df_c.columns: df_c['Tipo'] = ""
                    
                    indivs = df_c[df_c['Tipo'] == 'INDIVIDUAL']['Empleado'].unique().tolist()
                    sel_users = st.multiselect("Filtrar Empleados:", sorted(indivs), default=sorted(indivs))
                    
                    events = []
                    for _, r in df_c.iterrows():
                        ver = False
                        col = "#3788d8"
                        tit = ""
                        
                        if r['Tipo'] == 'GLOBAL':
                            ver, col, tit = True, "#FF5733", f"🏢 {r.get('Motivo')}"
                        elif r['Tipo'] == 'INDIVIDUAL' and r['Empleado'] in sel_users:
                            ver, col, tit = True, "#28B463", f"✈️ {r['Empleado']}: {r.get('Motivo')}"
                        
                        if ver:
                            try:
                                d_iso = datetime.strptime(r['Fecha'], "%d/%m/%Y").strftime("%Y-%m-%d")
                                events.append({
                                    "title": tit, "start": d_iso, "end": d_iso, 
                                    "backgroundColor": col, "allDay": True
                                })
                            except: pass
                    
                    # RENDERIZADO DEL CALENDARIO
                    if events:
                        calendar_options = {
                            "editable": False,
                            "height": 700,
                            "headerToolbar": {
                                "left": "today prev,next",
                                "center": "title",
                                "right": "dayGridMonth,listMonth"
                            },
                            "initialView": "dayGridMonth",
                            "locale": "es"
                        }
                        calendar(events=events, options=calendar_options, key="cal_widget")
                    else:
                        st.info("No hay eventos que mostrar.")
                else:
                    st.warning("No hay datos en el calendario.")

        # --- 3. AUDITORÍA ---
        elif opcion == "Auditoría e Informes":
            st.header("🕵️ Auditoría")
            data = cargar_datos_registros()
            
            if data:
                df = pd.DataFrame(data)
                
                # Procesamiento
                df['Estado'] = df.apply(verificar_integridad, axis=1)
                df['DT'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                df = df.sort_values(by='DT', ascending=False)
                df['Mes'] = df['DT'].dt.strftime('%m/%Y')
                
                # Filtros
                c1, c2 = st.columns(2)
                meses = ["Todos"] + sorted(df['Mes'].dropna().unique().tolist(), reverse=True)
                f_mes = c1.selectbox("Mes:", meses)
                
                emps_source = df[df['Mes'] == f_mes] if f_mes != "Todos" else df
                emps = ["Todos"] + sorted(emps_source['Empleado'].unique().tolist())
                f_emp = c2.selectbox("Empleado:", emps)
                
                # Filtrado final
                df_f = df.copy()
                if f_mes != "Todos": df_f = df_f[df_f['Mes'] == f_mes]
                if f_emp != "Todos": df_f = df_f[df_f['Empleado'] == f_emp]
                
                # Cálculo Horas
                tot_s = 0
                for e in df_f['Empleado'].unique():
                    sub = df_f[df_f['Empleado'] == e].sort_values(by='DT')
                    ent = None
                    for _, r in sub.iterrows():
                        if r['Tipo'] == 'ENTRADA': ent = r['DT']
                        elif r['Tipo'] == 'SALIDA' and ent:
                            tot_s += (r['DT'] - ent).total_seconds()
                            ent = None
