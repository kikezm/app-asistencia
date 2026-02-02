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
from streamlit_calendar import calendar

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

# --- CONEXIÓN A GOOGLE SHEETS (SIN CACHÉ, SOLO CONEXIÓN) ---
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
        st.error(f"❌ No encuentro la pestaña '{nombre_hoja_especifica}'.")
        st.stop()
    except gspread.SpreadsheetNotFound:
        st.error(f"❌ No encuentro la hoja: '{SHEET_NAME}'.")
        st.stop()

# --- FUNCIONES DE LECTURA OPTIMIZADAS (CON CACHÉ) ---
# TTL = Time To Live (Tiempo que dura en memoria antes de volver a leer)

@st.cache_data(ttl=600) # Guardar en memoria 10 minutos
def cargar_usuarios():
    sheet = conectar_google_sheets("Usuarios")
    return sheet.get_all_records()

@st.cache_data(ttl=600) # Guardar en memoria 10 minutos
def cargar_calendario():
    sheet = conectar_google_sheets("Calendario")
    return sheet.get_all_records()

@st.cache_data(ttl=60) # Guardar en memoria solo 60 segundos (porque cambia mucho)
def cargar_registros():
    sheet = conectar_google_sheets("Hoja 1")
    return sheet.get_all_records()

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
        # USAMOS LA VERSIÓN CACHEADA
        records = cargar_usuarios()
        token_limpio = str(token).strip()
        for row in records:
            if str(row['ID']).strip() == token_limpio: return row['Nombre']
        return None
    except: return None

def obtener_estado_actual(nombre_empleado):
    try:
        # USAMOS LA VERSIÓN CACHEADA
        data = cargar_registros()
        if not data: return "FUERA"
        df = pd.DataFrame(data)
        if 'Empleado' not in df.columns: return "FUERA"
        
        df_emp = df[df['Empleado'] == nombre_empleado]
        if df_emp.empty: return "FUERA"
        
        df_emp['FechaHora'] = pd.to_datetime(df_emp['Fecha'] + ' ' + df_emp['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        df_emp = df_emp.sort_values(by='FechaHora')
        
        return "DENTRO" if df_emp.iloc[-1]['Tipo'] == "ENTRADA" else "FUERA"
    except: return "DESCONOCIDO"

def puede_fichar_hoy(nombre_empleado):
    try:
        # USAMOS LA VERSIÓN CACHEADA
        registros = cargar_calendario()
        hoy = datetime.now().strftime("%d/%m/%Y")
        for row in registros:
            if row['Fecha'] == hoy:
                if row['Tipo'] == "GLOBAL": return False, f"Festivo: {row['Motivo']}"
                if row['Tipo'] == "INDIVIDUAL" and row['Empleado'] == nombre_empleado: return False, f"Vacaciones: {row['Motivo']}"
        return True, "OK"
    except: return True, "OK"

def registrar_fichaje(nombre, tipo, info_dispositivo):
    try:
        sheet = conectar_google_sheets("Hoja 1") 
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M:%S")
        firma = generar_firma(fecha, hora, nombre, tipo, info_dispositivo)
        sheet.append_row([fecha, hora, nombre, tipo, info_dispositivo, firma])
        
        # IMPORTANTE: BORRAMOS LA CACHÉ PARA QUE SE ACTUALICE AL INSTANTE
        st.cache_data.clear()
        
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
        puede_trabajar, motivo = puede_fichar_hoy(nombre_usuario)
        
        if not puede_trabajar:
            st.error(f"⛔ NO PUEDES FICHAR HOY")
            st.warning(f"Motivo: **{motivo}**")
        else:
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
            st.header("📅 Calendario Laboral")
            tab_gestion, tab_visual = st.tabs(["✍️ Gestión y Edición", "👀 Vista Gráfica Interactiva"])
            
            with tab_gestion:
                st.info("Bloquea vacaciones o festivos por rangos de fechas.")
                with st.form("nuevo_bloqueo_masivo"):
                    col1, col2 = st.columns(2)
                    with col1: fecha_inicio = st.date_input("Fecha Inicio", format="DD/MM/YYYY")
                    with col2: fecha_fin = st.date_input("Fecha Fin", value=fecha_inicio, format="DD/MM/YYYY")
                    
                    st.write("---")
                    col3, col4 = st.columns(2)
                    with col3:
                        tipo_bloqueo = st.selectbox("Tipo", ["INDIVIDUAL (Un empleado)", "GLOBAL (Toda la empresa)"])
                        nombre_emp_cal = "TODOS"
                        if "INDIVIDUAL" in tipo_bloqueo:
                            records = cargar_usuarios() # USAMOS CACHÉ
                            lista_nombres = [r['Nombre'] for r in records] if records else []
                            nombre_emp_cal = st.selectbox("Empleado Afectado:", lista_nombres)
                    
                    with col4:
                        modo_seleccion = st.radio("¿Qué días bloquear?", ["Todos los días del rango", "Solo Fines de Semana (Sáb/Dom)"])
                    
                    motivo = st.text_input("Motivo")
                    submit_cal = st.form_submit_button("💾 Guardar Fechas")
                    
                    if submit_cal and motivo:
                        try:
                            sheet_cal = conectar_google_sheets("Calendario")
                            filas_a_guardar = []
                            tipo_str = "GLOBAL" if "GLOBAL" in tipo_bloqueo else "INDIVIDUAL"
                            delta = fecha_fin - fecha_inicio
                            for i in range(delta.days + 1):
                                dia_actual = fecha_inicio + timedelta(days=i)
                                es_finde = dia_actual.weekday() >= 5
                                guardar = False
                                if modo_seleccion == "Todos los días del rango": guardar = True
                                elif modo_seleccion == "Solo Fines de Semana (Sáb/Dom)" and es_finde: guardar = True
                                if guardar:
                                    filas_a_guardar.append([dia_actual.strftime("%d/%m/%Y"), tipo_str, nombre_emp_cal, motivo])
                            
                            if filas_a_guardar:
                                sheet_cal.append_rows(filas_a_guardar)
                                st.cache_data.clear() # LIMPIAR CACHÉ
                                st.success(f"✅ {len(filas_a_guardar)} días añadidos.")
                                time.sleep(1)
                                st.rerun()
                        except Exception as e: st.error(f"Error: {e}")

                st.write("---")
                with st.expander("📂 Ver y Modificar Tabla"):
                    try:
                        data_cal = cargar_calendario() # USAMOS CACHÉ
                        if data_cal:
                            df_cal = pd.DataFrame(data_cal)
                            df_cal['F_Ord'] = pd.to_datetime(df_cal['Fecha'], format='%d/%m/%Y', errors='coerce')
                            df_cal = df_cal.sort_values(by='F_Ord', ascending=True).drop(columns=['F_Ord'])
                            
                            edited_df = st.data_editor(df_cal, num_rows="dynamic", use_container_width=True, hide_index=True)
                            
                            if st.button("💾 Guardar Cambios Tabla"):
                                sheet_cal = conectar_google_sheets("Calendario")
                                df_final = edited_df.copy()
                                df_final['Aux'] = pd.to_datetime(df_final['Fecha'], format='%d/%m/%Y', errors='coerce')
                                df_final = df_final.dropna(subset=['Aux']).sort_values(by='Aux', ascending=True).drop(columns=['Aux'])
                                nuevos_datos = [df_final.columns.values.tolist()] + df_final.values.tolist()
                                sheet_cal.clear()
                                sheet_cal.update(nuevos_datos)
                                st.cache_data.clear() # LIMPIAR CACHÉ
                                st.success("✅ Actualizado.")
                                time.sleep(1)
                                st.rerun()
                    except: pass

            with tab_visual:
                try:
                    raw_data = cargar_calendario() # USAMOS CACHÉ
                    if raw_data:
                        df_graf = pd.DataFrame(raw_data)
                        if 'Tipo' not in df_graf.columns: df_graf['Tipo'] = ""
                        if 'Empleado' not in df_graf.columns: df_graf['Empleado'] = ""
                        
                        emps = df_graf[df_graf['Tipo'] == 'INDIVIDUAL']['Empleado'].unique().tolist()
                        if not emps: emps = ["Sin datos"]
                        
                        sel = st.multiselect("Filtrar:", sorted(emps), default=sorted(emps))
                        
                        events = []
                        for _, row in df_graf.iterrows():
                            mostrar = False
                            color = "#3788d8"
                            if row.get('Tipo') == 'GLOBAL':
                                mostrar, color, tit = True, "#FF5733", f"🏢 {row.get('Motivo')}"
                            elif row.get('Tipo') == 'INDIVIDUAL' and row.get('Empleado') in sel:
                                mostrar, color, tit = True, "#28B463", f"✈️ {row.get('Empleado')}: {row.get('Motivo')}"
                            
                            if mostrar:
                                try:
                                    f_iso = datetime.strptime(row.get('Fecha'), "%d/%m/%Y").strftime("%Y-%m-%d")
                                    events.append({"title": tit, "start": f_iso, "end": f_iso, "backgroundColor": color, "allDay": True})
                                except: pass
                        
                        if events:
                            calendar(events=events, options={"initialView": "dayGridMonth", "height": 650, "locale": "es"}, key="mi_calendario")
                except Exception as e: st.error(f"Error gráfico: {e}")

        # --- SECCIÓN: USUARIOS ---
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
                        st.cache_data.clear() # LIMPIAR CACHÉ
                        st.success(f"Creado: {nuevo_nombre}")
                        st.code(f"{APP_URL}/?token={nuevo_id}")
                    except Exception as e: st.error(f"Error: {e}")

        # --- SECCIÓN: AUDITORÍA ---
        elif opcion == "Auditoría e Informes":
            st.header("🕵️ Auditoría")
            try:
                data = cargar_registros() # USAMOS CACHÉ
                if data:
                    df = pd.DataFrame(data)
                    df['Estado'] = df.apply(verificar_integridad, axis=1)
                    df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                    df = df.sort_values(by='FechaHora', ascending=False)
                    df['Mes_Año'] = df['FechaHora'].dt.strftime('%m/%Y')
                    
                    c1, c2 = st.columns(2)
                    with c1: 
                        meses = ["Todos"] + sorted(df['Mes_Año'].unique().tolist(), reverse=True)
                        f_mes = st.selectbox("Mes:", meses)
                    with c2:
                        emps = df[df['Mes_Año'] == f_mes]['Empleado'].unique() if f_mes != "Todos" else df['Empleado'].unique()
                        f_emp = st.selectbox("Empleado:", ["Todos"] + sorted(list(emps)))
                    
                    df_final = df.copy()
                    if f_mes != "Todos": df_final = df_final[df_final['Mes_Año'] == f_mes]
                    if f_emp != "Todos": df_final = df_final[df_final['Empleado'] == f_emp]
                    
                    # Cálculo horas
                    tot = 0
                    for e in df_final['Empleado'].unique():
                        sub = df_final[df_final['Empleado'] == e].sort_values(by='FechaHora')
                        ent = None
                        for _, r in sub.iterrows():
                            if r['Tipo'] == 'ENTRADA': ent = r['FechaHora']
                            elif r['Tipo'] == 'SALIDA' and ent:
                                tot += (r['FechaHora'] - ent).total_seconds()
                                ent = None
                    ht, mt = int(tot // 3600), int((tot % 3600) // 60)
                    
                    st.metric("Horas (Selección)", f"{ht}h {mt}m")
                    cols = ['Fecha', 'Hora', 'Empleado', 'Tipo', 'Estado', 'Dispositivo']
                    for c in cols: 
                        if c not in df_final.columns: df_final[c]=""
                    st.dataframe(df_final.reindex(columns=cols), use_container_width=True)
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_final.reindex(columns=cols).to_excel(writer, sheet_name='Reporte', index=False)
                        df_final.to_excel(writer, sheet_name='Datos', index=False)
                    buffer.seek(0)
                    st.download_button("📥 Descargar Excel", buffer, "Reporte.xlsx")
                else: st.warning("Sin datos.")
            except Exception as e: st.error(f"Error: {e}")

    elif password:
        st.error("Contraseña incorrecta")
