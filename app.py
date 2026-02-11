import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, time as datetime_time
import time
import os
import streamlit_javascript as st_js
import io
import uuid
import hashlib
from streamlit_calendar import calendar 
import pytz 

# --- CONFIGURACIÓN DE ZONA HORARIA ---
ZONA_HORARIA = pytz.timezone('Europe/Madrid')

def obtener_ahora():
    """Devuelve la fecha y hora actual exacta en tu zona horaria"""
    return datetime.now(ZONA_HORARIA)

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Control Asistencia", page_icon="🛡️")

# --- CARGA DE SECRETOS ---
try:
    SECRET_KEY = st.secrets["general"]["secret_key"]
    ADMIN_PASSWORD = st.secrets["general"]["admin_password"]
    SHEET_NAME = st.secrets["general"]["sheet_name"]
    # Si no tienes APP_URL en secrets, usa una por defecto para evitar errores
    APP_URL = st.secrets["general"].get("app_url", "https://tu-app.streamlit.app")
except Exception as e:
    st.error(f"⚠️ Error Crítico: Faltan secretos de configuración. {e}")
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

# --- FUNCIONES DE LECTURA CON CACHÉ INTELIGENTE Y REINTENTOS ---
def leer_con_reintento(nombre_hoja):
    max_intentos = 3
    for i in range(max_intentos):
        try:
            sheet = conectar_google_sheets(nombre_hoja)
            if sheet:
                return sheet.get_all_records()
            return []
        except Exception as e:
            if i == max_intentos - 1:
                st.error(f"⚠️ Error de conexión con Google Sheets ({nombre_hoja}): {e}")
                return []
            time.sleep(2 * (i + 1)) 
    return []

@st.cache_data(ttl=600)
def cargar_datos_usuarios():
    return leer_con_reintento("Usuarios")

@st.cache_data(ttl=600)
def cargar_datos_calendario():
    return leer_con_reintento("Calendario")

@st.cache_data(ttl=60)
def cargar_datos_registros():
    return leer_con_reintento("Hoja 1")

# --- FUNCIONES LÓGICAS ---
def generar_firma(fecha, hora, nombre, tipo, dispositivo):
    datos = f"{fecha}{hora}{nombre}{tipo}{dispositivo}{SECRET_KEY}"
    return hashlib.sha256(datos.encode()).hexdigest()

def verificar_integridad(row):
    try:
        firma = row.get('Firma', '')
        if not firma: return "❌ SIN FIRMA (MANUAL)"
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
    if not data: return "FUERA", None
    
    df = pd.DataFrame(data)
    if 'Empleado' not in df.columns: return "FUERA", None
    
    df_emp = df[df['Empleado'] == nombre]
    if df_emp.empty: return "FUERA", None
    
    df_emp = df_emp.dropna(subset=['Fecha', 'Hora'])
    df_emp['DT'] = pd.to_datetime(df_emp['Fecha'] + ' ' + df_emp['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    df_emp = df_emp.sort_values(by='DT')
    
    if df_emp.empty: return "FUERA", None
    
    ultimo = df_emp.iloc[-1]
    return ("DENTRO", ultimo['Hora']) if ultimo['Tipo'] == "ENTRADA" else ("FUERA", None)

def puede_fichar_hoy(nombre):
    data = cargar_datos_calendario()
    hoy = obtener_ahora().strftime("%d/%m/%Y")
    for r in data:
        if r.get('Fecha') == hoy:
            if r.get('Tipo') == "GLOBAL": return False, f"Festivo: {r.get('Motivo')}"
            if r.get('Tipo') == "INDIVIDUAL" and r.get('Empleado') == nombre: return False, f"Vacaciones: {r.get('Motivo')}"
    return True, "OK"

def registrar_fichaje(nombre, tipo, disp):
    try:
        sheet = conectar_google_sheets("Hoja 1")
        if not sheet: st.error("Error conectando a Hoja 1"); return

        ahora = obtener_ahora()
        f, h = ahora.strftime("%d/%m/%Y"), ahora.strftime("%H:%M:%S")
        
        firma = generar_firma(f, h, nombre, tipo, disp)
        sheet.append_row([f, h, nombre, tipo, disp, firma])
        
        st.cache_data.clear()
        st.success(f"✅ {tipo} registrada correctamente a las {h}.")
        time.sleep(2)
        st.rerun()
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# --- HELPER: PALETA DE ALTO CONTRASTE ---
def obtener_color_por_nombre(nombre):
    colores_contrastados = [
        "#E6194B", "#3CB44B", "#D4C200", "#4363D8", "#F58231", 
        "#911EB4", "#42D4F4", "#F032E6", "#BFEF45", "#FABED4", 
        "#469990", "#DCBEFF", "#9A6324", "#800000", "#AAFFC3", 
        "#808000", "#000075", "#A9A9A9"
    ]
    indice = abs(hash(nombre)) % len(colores_contrastados)
    return colores_contrastados[indice]

# --- INTERFAZ PRINCIPAL ---
try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

params = st.query_params
token_acceso = params.get("token", None)

st.title("🛡️ Control de Asistencia")

# ==========================================
# 1. CASO: ACCESO ADMINISTRADOR (Token Secreto)
# ==========================================
if token_acceso == "ADMIN": 
    st.sidebar.title("🔐 Administración")
    pwd = st.sidebar.text_input("Contraseña", type="password")
    
    if pwd == ADMIN_PASSWORD:
        st.sidebar.success("Acceso Concedido")
        
        # MENÚ LIMPIO (Ya no está el generador)
        menu = ["Generar Usuarios", "Calendario y Festivos", "🔧 Corrección de Fichajes", "Auditoría e Informes"]
        opcion = st.sidebar.radio("Ir a:", menu)
        
        # --- A. USUARIOS ---
        if opcion == "Generar Usuarios":
            st.header("👥 Gestión de Empleados")
            
            # Formulario
            with st.form("new_user"):
                st.subheader("Nuevo Alta")
                n_nombre = st.text_input("Nombre Completo")
                if st.form_submit_button("Crear Empleado"):
                    if n_nombre:
                        sheet = conectar_google_sheets("Usuarios")
                        uid = str(uuid.uuid4())
                        sheet.append_row([uid, n_nombre])
                        st.cache_data.clear()
                        st.success(f"✅ Creado: {n_nombre}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("El nombre no puede estar vacío.")
            
            # Tabla Usuarios
            st.write("---")
            st.subheader("📋 Directorio de Accesos")
            usuarios = cargar_datos_usuarios()
            if usuarios:
                df_u = pd.DataFrame(usuarios)
                if 'ID' in df_u.columns and 'Nombre' in df_u.columns:
                    base = APP_URL
                    df_u['Enlace de Acceso'] = df_u['ID'].apply(lambda x: f"{base}/?token={x}")
                    df_mostrar = df_u[['Nombre', 'Enlace de Acceso']]
                    
                    st.dataframe(
                        df_mostrar,
                        column_config={
                            "Nombre": st.column_config.TextColumn("Empleado", width="medium"),
                            "Enlace de Acceso": st.column_config.LinkColumn("Link Directo", display_text=f"{base}/?token=...")
                        },
                        hide_index=True, use_container_width=True
                    )
                    with st.expander("Ver enlaces en texto plano (Copiar/Pegar)"):
                        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
                else: st.error("Error columnas Usuarios.")
            else: st.info("No hay usuarios.")

        # --- B. CALENDARIO ---
        elif opcion == "Calendario y Festivos":
            st.header("📅 Calendario Laboral")
            t_gest, t_vis = st.tabs(["✍️ Gestión (Añadir/Borrar)", "👀 Visualizar"])
            
            with t_gest:
                st.subheader("1. Añadir Nuevos Días")
                with st.form("add_cal"):
                    rango_fechas = st.date_input("Selecciona Rango", value=[], format="DD/MM/YYYY")
                    c3, c4 = st.columns(2)
                    with c3:
                        tipo = st.selectbox("Tipo", ["INDIVIDUAL (Un empleado)", "GLOBAL (Empresa)"])
                        nom_emp = "TODOS"
                        if "INDIVIDUAL" in tipo:
                            usrs = cargar_datos_usuarios()
                            l_n = [u['Nombre'] for u in usrs] if usrs else []
                            nom_emp = st.selectbox("Empleado:", l_n)
                    with c4:
                        modo = st.radio("Días:", ["Todos", "Solo Fines de Semana"])
                    motivo = st.text_input("Motivo")
                    
                    if st.form_submit_button("➕ Añadir"):
                        if len(rango_fechas) == 0:
                            st.error("Selecciona fechas.")
                        else:
                            d_ini = rango_fechas[0]
                            d_fin = rango_fechas[1] if len(rango_fechas) > 1 else d_ini
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
                                st.cache_data.clear()
                                st.success("Añadido.")
                                time.sleep(1)
                                st.rerun()

                st.write("---")
                st.subheader("2. 📝 Modificar o Borrar")
                st.info("Haz clic en una celda para editar. Selecciona fila y pulsa Supr para borrar.")
                
                data = cargar_datos_calendario()
                if data:
                    df = pd.DataFrame(data)
                    if 'Fecha' in df.columns:
                        df['Aux'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
                        df = df.sort_values(by='Aux', ascending=False).drop(columns=['Aux'])
                    
                    df_editado = st.data_editor(
                        df, num_rows="dynamic", use_container_width=True, key="editor_vacaciones",
                        column_config={
                            "Fecha": st.column_config.TextColumn("Fecha (DD/MM/YYYY)"),
                            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["GLOBAL", "INDIVIDUAL"]),
                        }
                    )
                    
                    if st.button("💾 Guardar Cambios Tabla", type="primary"):
                        try:
                            vals = [df_editado.columns.values.tolist()] + df_editado.values.tolist()
                            sheet = conectar_google_sheets("Calendario")
                            sheet.clear()
                            sheet.update(vals)
                            st.cache_data.clear()
                            st.success("Calendario actualizado.")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e: st.error(e)
            
            with t_vis:
                raw_cal = cargar_datos_calendario()
                if raw_cal:
                    df_c = pd.DataFrame(raw_cal)
                    if 'Empleado' not in df_c.columns: df_c['Empleado'] = ""
                    if 'Tipo' not in df_c.columns: df_c['Tipo'] = ""
                    if 'Fecha' not in df_c.columns: df_c['Fecha'] = ""
                    if 'Motivo' not in df_c.columns: df_c['Motivo'] = ""
                    
                    df_c = df_c[df_c['Fecha'].astype(bool)]
                    indivs = df_c[df_c['Tipo'] == 'INDIVIDUAL']['Empleado'].unique().tolist()
                    sel_users = st.multiselect("Filtrar Empleados:", sorted(indivs), default=sorted(indivs))
                    
                    events = []
                    for _, r in df_c.iterrows():
                        ver, col, tit = False, "#3788d8", ""
                        tipo_r = str(r.get('Tipo', '')).strip()
                        emp_r = str(r.get('Empleado', '')).strip()
                        fecha_r = str(r.get('Fecha', '')).strip()
                        motivo_r = str(r.get('Motivo', '')).strip()
                        
                        if tipo_r == 'GLOBAL':
                            ver, col, tit = True, "#000000", f"🏢 {motivo_r}"
                        elif tipo_r == 'INDIVIDUAL' and emp_r in sel_users:
                            ver, col, tit = True, obtener_color_por_nombre(emp_r), emp_r
                        
                        if ver and fecha_r:
                            try:
                                d_iso = datetime.strptime(fecha_r, "%d/%m/%Y").strftime("%Y-%m-%d")
                                events.append({"title": tit, "start": d_iso, "end": d_iso, "backgroundColor": col, "borderColor": col, "allDay": True, "textColor": "#FFFFFF"})
                            except: pass 
                    
                    if events:
                        calendar(events=events, options={
                            "editable": False, "height": 700, 
                            "initialDate": datetime.now().strftime("%Y-%m-%d"),
                            "headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth,listMonth"},
                            "initialView": "dayGridMonth", "locale": "es", "firstDay": 1,
                            "buttonText": {"today": "Hoy", "month": "Mes", "list": "Lista"}
                        }, key=f"cal_admin_{len(events)}_{len(sel_users)}")
                        st.caption("⬛ Festivos | 🎨 Vacaciones")
                    else: st.info("No hay eventos.")

        # --- C. CORRECCIÓN ---
        elif opcion == "🔧 Corrección de Fichajes":
            st.header("🔧 Insertar Fichaje Manual")
            st.warning("⚠️ El registro aparecerá como 'SIN FIRMA' en la auditoría.")
            with st.form("manual_entry"):
                col_a, col_b = st.columns(2)
                usrs = cargar_datos_usuarios()
                lista_n = [u['Nombre'] for u in usrs] if usrs else []
                with col_a:
                    emp_manual = st.selectbox("Empleado:", lista_n)
                    fecha_manual = st.date_input("Fecha:", format="DD/MM/YYYY")
                with col_b:
                    tipo_manual = st.selectbox("Tipo:", ["ENTRADA", "SALIDA"])
                    hora_manual = st.time_input("Hora (HH:MM):", step=60)
                motivo_manual = st.text_input("Motivo:")
                
                if st.form_submit_button("💾 Guardar"):
                    try:
                        sheet = conectar_google_sheets("Hoja 1")
                        f_str, h_str = fecha_manual.strftime("%d/%m/%Y"), hora_manual.strftime("%H:%M:%S")
                        sheet.append_row([f_str, h_str, emp_manual, tipo_manual, f"MANUAL (Admin) - {motivo_manual}", ""])
                        st.cache_data.clear()
                        st.success("✅ Registro añadido.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e: st.error(e)

        # --- D. AUDITORÍA ---
        elif opcion == "Auditoría e Informes":
            st.header("🕵️ Auditoría")
            data = cargar_datos_registros()
            if data:
                df = pd.DataFrame(data).dropna(subset=['Fecha', 'Hora'])
                df['Estado'] = df.apply(verificar_integridad, axis=1)
                df['DT'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                df = df.sort_values(by='DT', ascending=False)
                df['Mes'] = df['DT'].dt.strftime('%m/%Y')
                
                c1, c2 = st.columns(2)
                meses = ["Todos"] + sorted(df['Mes'].dropna().unique().tolist(), reverse=True)
                f_mes = c1.selectbox("Mes:", meses)
                emps = ["Todos"] + sorted(df['Empleado'].unique().tolist())
                f_emp = c2.selectbox("Empleado:", emps)
                
                df_f = df.copy()
                if f_mes != "Todos": df_f = df_f[df_f['Mes'] == f_mes]
                if f_emp != "Todos": df_f = df_f[df_f['Empleado'] == f_emp]
                
                tot_s = 0
                for e in df_f['Empleado'].unique():
                    sub = df_f[df_f['Empleado'] == e].sort_values(by='DT')
                    ent = None
                    for _, r in sub.iterrows():
                        if r['Tipo'] == 'ENTRADA': ent = r['DT']
                        elif r['Tipo'] == 'SALIDA' and ent:
                            tot_s += (r['DT'] - ent).total_seconds()
                            ent = None
                st.metric("Horas Trabajadas", f"{int(tot_s // 3600)}h {int((tot_s % 3600) // 60)}m")
                
                t_list, t_cal = st.tabs(["📄 Lista", "📅 Calendario Horas"])
                with t_list:
                    cols = ['Fecha', 'Hora', 'Empleado', 'Tipo', 'Estado', 'Dispositivo']
                    st.dataframe(df_f.reindex(columns=cols), use_container_width=True)
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_f.reindex(columns=cols).to_excel(writer, index=False)
                    st.download_button("📥 Excel", buffer.getvalue(), "Reporte.xlsx")

                with t_cal:
                    if f_emp == "Todos":
                        st.info("Selecciona un empleado para ver sus horas diarias.")
                    else:
                        df_calc = df_f.sort_values(by='DT')
                        horas_dia, ent = {}, None
                        for _, r in df_calc.iterrows():
                            if r['Tipo'] == 'ENTRADA': ent = r['DT']
                            elif r['Tipo'] == 'SALIDA' and ent:
                                d = (r['DT'] - ent).total_seconds()
                                k = ent.strftime("%Y-%m-%d")
                                horas_dia[k] = horas_dia.get(k, 0) + d
                                ent = None
                        
                        evs = []
                        for k, v in horas_dia.items():
                            h, m = int(v//3600), int((v%3600)//60)
                            c = "#1976D2"
                            if h < 5: c = "#D32F2F"
                            elif h < 8: c = "#F57C00"
                            evs.append({"title": f"⏱️ {h}h {m}m", "start": k, "end": k, "allDay": True, "backgroundColor": c, "borderColor": c, "textColor": "#FFF"})
                        
                        if evs:
                            calendar(events=evs, options={
                                "initialDate": datetime.now().strftime("%Y-%m-%d"),
                                "headerToolbar": {"left": "prev,next", "center": "title", "right": "dayGridMonth"},
                                "initialView": "dayGridMonth", "locale": "es", "firstDay": 1
                            }, key=f"audit_{f_emp}")
                            st.caption("🔵 >8h | 🟠 5-8h | 🔴 <5h")
                        else: st.warning("Sin datos completos.")

    elif pwd:
        st.error("⛔ Contraseña incorrecta")

# ==========================================
# 2. CASO: ACCESO EMPLEADO (Token UUID)
# ==========================================
elif token_acceso:
    nombre = obtener_nombre_por_token(token_acceso)
    
    if nombre:
        st.info(f"👋 Hola, **{nombre}**")
        tab_fichar, tab_mis_vacaciones = st.tabs(["🕒 Fichar", "📅 Calendario de Equipo"])
        
        with tab_fichar:
            ok, motivo = puede_fichar_hoy(nombre)
            
            if not ok:
                st.error("⛔ NO PUEDES FICHAR HOY")
                st.warning(f"Motivo: **{motivo}**")
            else:
                estado, hora_entrada = obtener_estado_actual(nombre)
                st.write("---")
                
                if estado == "FUERA":
                    st.markdown("### 🏠 Estás FUERA. ¿Entrar?")
                    
                    # --- NUEVA FUNCIONALIDAD: SALIDA AUTOMÁTICA ---
                    with st.expander("⚙️ Opciones de Entrada (Auto-Salida)"):
                        usar_auto = st.checkbox("🔄 Fichar Salida automáticamente hoy")
                        if usar_auto:
                            # Por defecto ponemos las 17:00 (o la hora que prefieras)
                            hora_auto = st.time_input("Hora de Salida prevista:", value=datetime_time(17, 0))
                    
                    if st.button("🟢 ENTRADA", use_container_width=True): 
                        # 1. Registramos la ENTRADA normal
                        registrar_fichaje(nombre, "ENTRADA", ua_string)
                        
                        # 2. Si marcó el check, registramos la SALIDA futura inmediatamente
                        if usar_auto:
                            try:
                                sheet = conectar_google_sheets("Hoja 1")
                                ahora = obtener_ahora()
                                f_str = ahora.strftime("%d/%m/%Y")
                                h_str = hora_auto.strftime("%H:%M:%S")
                                
                                # Indicamos en el dispositivo que fue programado
                                disp_auto = f"{ua_string} (Auto-Programada)"
                                
                                # Generamos firma válida para esa hora futura
                                firma = generar_firma(f_str, h_str, nombre, "SALIDA", disp_auto)
                                
                                # Insertamos la fila
                                sheet.append_row([f_str, h_str, nombre, "SALIDA", disp_auto, firma])
                                st.toast(f"✅ Salida programada para las {h_str}")
                                
                            except Exception as e:
                                st.error(f"Error al programar salida: {e}")

                elif estado == "DENTRO":
                    h_c = hora_entrada[:5] if hora_entrada else ""
                    st.markdown(f"### 🏭 Has entrado a las **{h_c}**. ¿Salir?")
                    st.info("💡 Si ya programaste tu salida automática al entrar, no necesitas pulsar este botón (salvo que salgas antes de tiempo).")
                    
                    if st.button("🔴 SALIDA (Manual)", use_container_width=True): 
                        registrar_fichaje(nombre, "SALIDA", ua_string)

        with tab_mis_vacaciones:
            st.write("") 
            raw_cal = cargar_datos_calendario()
            if raw_cal:
                df_c = pd.DataFrame(raw_cal)
                if 'Empleado' not in df_c.columns: df_c['Empleado'] = ""
                if 'Tipo' not in df_c.columns: df_c['Tipo'] = ""
                if 'Fecha' not in df_c.columns: df_c['Fecha'] = ""
                if 'Motivo' not in df_c.columns: df_c['Motivo'] = ""
                
                df_c = df_c[df_c['Fecha'].astype(bool)]
                indivs = df_c[df_c['Tipo'] == 'INDIVIDUAL']['Empleado'].unique().tolist()
                sel_users = st.multiselect("Filtrar:", sorted(indivs), default=sorted(indivs))
                
                events = []
                for _, r in df_c.iterrows():
                    ver, col, tit = False, "#3788d8", ""
                    tipo_r = str(r.get('Tipo', '')).strip()
                    emp_r = str(r.get('Empleado', '')).strip()
                    fecha_r = str(r.get('Fecha', '')).strip()
                    motivo_r = str(r.get('Motivo', '')).strip()
                    
                    if tipo_r == 'GLOBAL':
                        ver, col, tit = True, "#000000", f"🏢 {motivo_r}"
                    elif tipo_r == 'INDIVIDUAL':
                        if emp_r in sel_users:
                            ver = True
                            if emp_r == nombre:
                                col, tit = "#109618", "TÚ"
                            else:
                                col, tit = obtener_color_por_nombre(emp_r), emp_r
                    
                    if ver and fecha_r:
                        try:
                            d_iso = datetime.strptime(fecha_r, "%d/%m/%Y").strftime("%Y-%m-%d")
                            events.append({"title": tit, "start": d_iso, "end": d_iso, "backgroundColor": col, "borderColor": col, "allDay": True, "textColor": "#FFFFFF"})
                        except: pass
                
                if events:
                    calendar(events=events, options={
                        "editable": False, "height": 650, 
                        "initialDate": datetime.now().strftime("%Y-%m-%d"),
                        "headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth,listMonth"},
                        "initialView": "dayGridMonth", "locale": "es", "firstDay": 1,
                        "buttonText": {"today": "Hoy", "month": "Mes", "list": "Lista"}
                    }, key=f"cal_user_{len(events)}_{len(sel_users)}")
                    st.caption("🏢 Festivos | 🟢 Tus Días | 🎨 Compañeros")
                else: st.info("No hay eventos.")
            else: st.warning("Calendario vacío.")
    else:
        st.error("⛔ Token inválido.")

# ==========================================
# 3. CASO: ZONA FANTASMA (Sin Token)
# ==========================================
else:
    st.markdown("""
        <style>
        .stApp { background-color: #000000; color: #333333; }
        </style>
        """, unsafe_allow_html=True)
    st.warning("⚠️ **Acceso Restringido**")
    st.write("Esta aplicación requiere un enlace de acceso seguro personal.")
