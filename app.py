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
import pytz # <--- NUEVA IMPORTACIÓN

# --- CONFIGURACIÓN DE ZONA HORARIA ---
# Cambia 'Europe/Madrid' por tu zona si es otra (ej: 'America/Mexico_City')
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

# --- FUNCIONES DE LECTURA CON CACHÉ INTELIGENTE Y REINTENTOS ---
# Esta función ayuda a reintentar si Google da error de "demasiadas peticiones"
def leer_con_reintento(nombre_hoja):
    max_intentos = 3
    for i in range(max_intentos):
        try:
            sheet = conectar_google_sheets(nombre_hoja)
            if sheet:
                return sheet.get_all_records()
            return []
        except Exception as e:
            # Si es el último intento, fallamos de verdad
            if i == max_intentos - 1:
                st.error(f"⚠️ Error de conexión con Google Sheets ({nombre_hoja}): {e}")
                return []
            # Si no, esperamos un poco (backoff exponencial) antes de reintentar
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
        # Si no hay firma, marcamos explícitamente como MANUAL/SIN FIRMA
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
    """Devuelve una tupla: (ESTADO, HORA_ULTIMO_MOVIMIENTO)"""
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
    # CAMBIO AQUÍ: Usamos la zona horaria para saber qué día es hoy
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

        # CAMBIO AQUÍ: Usamos la zona horaria configurada
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
    # Lista diseñada manualmente para máximo contraste visual
    # Evitamos gamas de azules o verdes seguidos.
    colores_contrastados = [
        "#E6194B", # Rojo brillante
        "#3CB44B", # Verde vibrante
        "#FFE119", # Amarillo (Ojo, usaremos texto negro con este si fuera auto, pero el blanco se lee regular, mejor ocre) -> Cambiado a Oro oscuro:
        "#D4C200", # Oro oscuro
        "#4363D8", # Azul fuerte
        "#F58231", # Naranja
        "#911EB4", # Violeta
        "#42D4F4", # Cian
        "#F032E6", # Magenta
        "#BFEF45", # Lima
        "#FABED4", # Rosa palo
        "#469990", # Verde azulado
        "#DCBEFF", # Lavanda
        "#9A6324", # Marrón
        "#800000", # Granate
        "#AAFFC3", # Verde menta
        "#808000", # Oliva
        "#000075", # Azul marino oscuro
        "#A9A9A9"  # Gris
    ]
    # Usamos hash para asignar siempre el mismo color al mismo nombre
    indice = abs(hash(nombre)) % len(colores_contrastados)
    return colores_contrastados[indice]

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
        
        # Creamos dos pestañas para el trabajador
        tab_fichar, tab_mis_vacaciones = st.tabs(["🕒 Fichar", "📅 Mis Vacaciones"])
        
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
                    if st.button("🟢 ENTRADA", use_container_width=True): 
                        registrar_fichaje(nombre, "ENTRADA", ua_string)
                elif estado == "DENTRO":
                    hora_corta = hora_entrada[:5] if hora_entrada and len(hora_entrada) >= 5 else hora_entrada
                    st.markdown(f"### 🏭 Has entrado a las **{hora_corta}**. ¿Salir?")
                    if st.button("🔴 SALIDA", use_container_width=True): 
                        registrar_fichaje(nombre, "SALIDA", ua_string)

        with tab_mis_vacaciones:
            st.subheader("📅 Calendario de Equipo")
            st.write("") # Pausa de carga
            
            raw_cal = cargar_datos_calendario()
            
            if raw_cal:
                df_c = pd.DataFrame(raw_cal)
                
                # Limpiezas
                if 'Empleado' not in df_c.columns: df_c['Empleado'] = ""
                if 'Tipo' not in df_c.columns: df_c['Tipo'] = ""
                if 'Fecha' not in df_c.columns: df_c['Fecha'] = ""
                if 'Motivo' not in df_c.columns: df_c['Motivo'] = ""
                
                df_c = df_c[df_c['Fecha'].astype(bool)]
                
                indivs = df_c[df_c['Tipo'] == 'INDIVIDUAL']['Empleado'].unique().tolist()
                
                sel_users = st.multiselect(
                    "Filtrar compañeros:", 
                    sorted(indivs), 
                    default=sorted(indivs)
                )
                
                events = []
                for _, r in df_c.iterrows():
                    ver, col, tit = False, "#3788d8", ""
                    
                    tipo_r = str(r.get('Tipo', '')).strip()
                    emp_r = str(r.get('Empleado', '')).strip()
                    fecha_r = str(r.get('Fecha', '')).strip()
                    motivo_r = str(r.get('Motivo', '')).strip()
                    
                    # LÓGICA VISUAL
                    if tipo_r == 'GLOBAL':
                        ver = True
                        col = "#000000" # Negro
                        # En festivos globales SÍ mostramos el motivo (ej: Navidad)
                        tit = f"🏢 {motivo_r}"
                    
                    elif tipo_r == 'INDIVIDUAL':
                        if emp_r in sel_users:
                            ver = True
                            if emp_r == nombre:
                                col = "#109618" # Verde para mí
                                # SOLO NOMBRE (o "TÚ" para diferenciarlo claro)
                                tit = "TÚ" 
                            else:
                                col = obtener_color_por_nombre(emp_r)
                                # CAMBIO AQUÍ: SOLO EL NOMBRE
                                tit = emp_r
                    
                    if ver and fecha_r:
                        try:
                            d_iso = datetime.strptime(fecha_r, "%d/%m/%Y").strftime("%Y-%m-%d")
                            events.append({
                                "title": tit, 
                                "start": d_iso, 
                                "end": d_iso, 
                                "backgroundColor": col, 
                                "borderColor": col,
                                "allDay": True,
                                "textColor": "#FFFFFF"
                            })
                        except: pass
                
                if events:
                    cal_opts_user = {
                        "editable": False,
                        "height": 650,
                        "initialDate": datetime.now().strftime("%Y-%m-%d"),
                        "headerToolbar": {
                            "left": "today prev,next",
                            "center": "title",
                            "right": "dayGridMonth,listMonth"
                        },
                        "initialView": "dayGridMonth",
                        "locale": "es",
                        "firstDay": 1,
                        "buttonText": {"today": "Hoy", "month": "Mes", "list": "Lista"}
                    }
                    
                    clave_user = f"cal_user_clean_{len(events)}_{len(sel_users)}"
                    calendar(events=events, options=cal_opts_user, key=clave_user)
                    st.caption("🏢 Festivos | 🟢 Tus Días | 🎨 Compañeros")
                else:
                    st.info("No hay eventos.")
            else:
                st.warning("Calendario vacío.")



# ==========================================
# VISTA ADMIN
# ==========================================
else:
    st.sidebar.title("Administración")
    # MENÚ NUEVO: Añadido "Corrección de Fichajes"
    menu = ["Generar Usuarios", "Calendario y Festivos", "🔧 Corrección de Fichajes", "Auditoría e Informes"]
    opcion = st.sidebar.radio("Ir a:", menu)
    pwd = st.sidebar.text_input("Contraseña", type="password")
    
    if pwd == ADMIN_PASSWORD:
        
        # --- 1. USUARIOS ---
        if opcion == "Generar Usuarios":
            st.header("👥 Gestión de Empleados")
            
            # A) Formulario de Creación
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
                        # Forzamos recarga para que salga en la tabla de abajo al instante
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("El nombre no puede estar vacío.")
            
            # B) Tabla de Usuarios Existentes (NUEVO)
            st.write("---")
            st.subheader("📋 Directorio de Accesos")
            
            usuarios = cargar_datos_usuarios()
            
            if usuarios:
                df_u = pd.DataFrame(usuarios)
                
                # Comprobamos que existan las columnas correctas
                if 'ID' in df_u.columns and 'Nombre' in df_u.columns:
                    # Creamos la columna del Link combinando la URL base con el Token
                    # APP_URL debe estar definido en tus secrets, si no, usa una cadena vacía o aviso
                    base = APP_URL if 'APP_URL' in globals() and APP_URL else "https://tu-app.streamlit.app"
                    
                    df_u['Enlace de Acceso'] = df_u['ID'].apply(lambda x: f"{base}/?token={x}")
                    
                    # Seleccionamos solo lo que nos interesa mostrar
                    df_mostrar = df_u[['Nombre', 'Enlace de Acceso']]
                    
                    # Mostramos la tabla. 
                    # Usamos LinkColumn para que sea clicable, o texto plano para copiar fácil.
                    st.dataframe(
                        df_mostrar,
                        column_config={
                            "Nombre": st.column_config.TextColumn("Empleado", width="medium"),
                            "Enlace de Acceso": st.column_config.LinkColumn(
                                "Link Directo (Clic para abrir)",
                                display_text=f"{base}/?token=..." # Muestra versión corta, el link real está detrás
                            )
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    # Opción extra por si quieren copiar el texto exacto masivamente
                    with st.expander("Ver enlaces en texto plano (Para copiar y pegar)"):
                        st.dataframe(df_mostrar, use_container_width=True, hide_index=True)
                        
                else:
                    st.error("Error: La hoja de 'Usuarios' no tiene las columnas ID y Nombre.")
            else:
                st.info("No hay usuarios registrados todavía.")
        
        # --- 2. CALENDARIO ---
        elif opcion == "Calendario y Festivos":
            st.header("📅 Calendario Laboral")
            t_gest, t_vis = st.tabs(["✍️ Gestión (Añadir/Borrar)", "👀 Visualizar"])
            
            with t_gest:
                # --- PARTE A: AÑADIR NUEVOS ---
                st.subheader("1. Añadir Nuevos Días")
                with st.form("add_cal"):
                    rango_fechas = st.date_input("Selecciona Rango (Inicio - Fin)", value=[], format="DD/MM/YYYY")
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
                    motivo = st.text_input("Motivo (Ej: Vacaciones Verano)")
                    
                    if st.form_submit_button("➕ Añadir al Calendario"):
                        if len(rango_fechas) == 0:
                            st.error("Debes seleccionar al menos una fecha.")
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
                                st.success(f"✅ Añadidos {len(rows)} días correctamente.")
                                time.sleep(1)
                                st.rerun()

                st.write("---")
                
                # --- PARTE B: MODIFICAR / BORRAR (MEJORADO) ---
                st.subheader("2. 📝 Modificar o Borrar Existentes")
                st.info("💡 **Instrucciones:** Haz clic en una celda para editarla. Selecciona las filas (checkbox izquierda) y pulsa **Suprimir** en tu teclado para borrarlas.")
                
                data = cargar_datos_calendario()
                if data:
                    df = pd.DataFrame(data)
                    
                    # Preparación de datos
                    if 'Fecha' in df.columns:
                        df['Aux'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
                        df = df.sort_values(by='Aux', ascending=False) # Ordenar: Mas reciente arriba
                        df = df.drop(columns=['Aux'])
                    
                    # TABLA EDITABLE
                    # num_rows="dynamic" permite añadir y BORRAR filas
                    df_editado = st.data_editor(
                        df, 
                        num_rows="dynamic", 
                        use_container_width=True,
                        key="editor_vacaciones",
                        column_config={
                            "Fecha": st.column_config.TextColumn("Fecha (DD/MM/YYYY)"),
                            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["GLOBAL", "INDIVIDUAL"]),
                            "Empleado": st.column_config.TextColumn("Empleado"),
                            "Motivo": st.column_config.TextColumn("Motivo")
                        }
                    )
                    
                    col_save, col_info = st.columns([1, 2])
                    with col_save:
                        if st.button("💾 Guardar Cambios Tabla", type="primary"):
                            try:
                                # Convertimos el DF editado a lista de listas
                                vals = [df_editado.columns.values.tolist()] + df_editado.values.tolist()
                                
                                sheet = conectar_google_sheets("Calendario")
                                sheet.clear() # Borramos todo
                                sheet.update(vals) # Escribimos lo nuevo (sin las filas borradas)
                                
                                st.cache_data.clear()
                                st.success("✅ Calendario actualizado correctamente.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al guardar: {e}")
                else:
                    st.warning("No hay datos en el calendario para editar.")

            # --- PESTAÑA VISUALIZAR (Mantenemos tu versión limpia) ---
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
                        clave_dinamica = f"cal_admin_clean_{len(events)}_{len(sel_users)}"
                        calendar(events=events, options={
                            "editable": False, "height": 700, 
                            "initialDate": datetime.now().strftime("%Y-%m-%d"),
                            "headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth,listMonth"},
                            "initialView": "dayGridMonth", "locale": "es", "firstDay": 1,
                            "buttonText": {"today": "Hoy", "month": "Mes", "list": "Lista"}
                        }, key=clave_dinamica)
                        st.caption("⬛ Festivos Empresa | 🎨 Vacaciones (Solo Nombre)")
                    else: st.info("No hay eventos.")
                else: st.warning("Sin datos.")



        # --- 3. NUEVO: CORRECCIÓN DE FICHAJES ---
        elif opcion == "🔧 Corrección de Fichajes":
            st.header("🔧 Insertar Fichaje Manual")
            st.warning("⚠️ Utiliza esto para corregir olvidos. El registro aparecerá como 'SIN FIRMA' en la auditoría.")
            
            with st.form("manual_entry"):
                col_a, col_b = st.columns(2)
                
                # Cargar lista empleados
                usrs = cargar_datos_usuarios()
                lista_n = [u['Nombre'] for u in usrs] if usrs else []
                
                with col_a:
                    emp_manual = st.selectbox("Empleado:", lista_n)
                    fecha_manual = st.date_input("Fecha:", format="DD/MM/YYYY")
                
                with col_b:
                    tipo_manual = st.selectbox("Tipo:", ["ENTRADA", "SALIDA"])
                    hora_manual = st.time_input("Hora (HH:MM):", step=60)
                
                motivo_manual = st.text_input("Motivo de la corrección (Opcional):", placeholder="Ej: Olvido al fichar")
                
                if st.form_submit_button("💾 Guardar Registro Manual"):
                    try:
                        sheet = conectar_google_sheets("Hoja 1")
                        f_str = fecha_manual.strftime("%d/%m/%Y")
                        h_str = hora_manual.strftime("%H:%M:%S")
                        
                        # Dispositivo = MANUAL (ADMIN)
                        disp_str = f"MANUAL (Admin) - {motivo_manual}"
                        
                        # FIRMA VACÍA ("") -> Esto provocará el aviso "SIN FIRMA"
                        sheet.append_row([f_str, h_str, emp_manual, tipo_manual, disp_str, ""])
                        
                        st.cache_data.clear()
                        st.success(f"✅ Registro añadido: {emp_manual} - {tipo_manual} a las {h_str}")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

# --- 4. AUDITORÍA E INFORMES (MEJORADO CON CALENDARIO) ---
        elif opcion == "Auditoría e Informes":
            st.header("🕵️ Auditoría y Control Horario")
            
            data = cargar_datos_registros()
            
            if data:
                df = pd.DataFrame(data)
                df = df.dropna(subset=['Fecha', 'Hora']) # Limpieza
                
                # Procesamiento previo
                df['Estado'] = df.apply(verificar_integridad, axis=1)
                df['DT'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
                df = df.sort_values(by='DT', ascending=False)
                df['Mes'] = df['DT'].dt.strftime('%m/%Y')
                
                # --- FILTROS SUPERIORES ---
                c1, c2 = st.columns(2)
                meses = ["Todos"] + sorted(df['Mes'].dropna().unique().tolist(), reverse=True)
                f_mes = c1.selectbox("Filtrar por Mes:", meses)
                
                emps_source = df[df['Mes'] == f_mes] if f_mes != "Todos" else df
                emps = ["Todos"] + sorted(emps_source['Empleado'].unique().tolist())
                f_emp = c2.selectbox("Filtrar por Empleado:", emps)
                
                # Filtrado de datos
                df_f = df.copy()
                if f_mes != "Todos": df_f = df_f[df_f['Mes'] == f_mes]
                if f_emp != "Todos": df_f = df_f[df_f['Empleado'] == f_emp]
                
                # --- CÁLCULO DE HORAS TOTALES (Para la métrica) ---
                tot_s = 0
                for e in df_f['Empleado'].unique():
                    sub = df_f[df_f['Empleado'] == e].sort_values(by='DT')
                    ent = None
                    for _, r in sub.iterrows():
                        if r['Tipo'] == 'ENTRADA': 
                            ent = r['DT']
                        elif r['Tipo'] == 'SALIDA' and ent:
                            tot_s += (r['DT'] - ent).total_seconds()
                            ent = None
                
                ht, mt = int(tot_s // 3600), int((tot_s % 3600) // 60)
                st.metric("Total Horas Trabajadas (Selección)", f"{ht}h {mt}m")
                st.write("---")

                # --- PESTAÑAS DE VISUALIZACIÓN ---
                tab_lista, tab_cal_horas = st.tabs(["📄 Vista de Lista (Excel)", "📅 Vista Calendario Horario"])

                # >>> PESTAÑA 1: TABLA (Lo que ya tenías)
                with tab_lista:
                    cols_vis = ['Fecha', 'Hora', 'Empleado', 'Tipo', 'Estado', 'Dispositivo']
                    st.dataframe(
                        df_f.reindex(columns=cols_vis), 
                        use_container_width=True,
                        column_config={
                            "Estado": st.column_config.TextColumn("Validación"),
                        }
                    )
                    
                    # Botón descarga
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_f.reindex(columns=cols_vis).to_excel(writer, sheet_name='Reporte', index=False)
                    buffer.seek(0)
                    file_n = f"Reporte_{f_emp}_{f_mes.replace('/','-')}.xlsx"
                    st.download_button("📥 Descargar Excel", buffer, file_n, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                # >>> PESTAÑA 2: CALENDARIO DE HORAS TRABAJADAS (NUEVO)
                with tab_cal_horas:
                    if f_emp == "Todos":
                        st.info("👈 Por favor, selecciona un **Empleado concreto** arriba para calcular sus horas diarias.")
                        st.caption("El cálculo de horas diarias en calendario no está disponible para 'Todos' a la vez.")
                    else:
                        # Lógica para agrupar horas POR DÍA
                        # 1. Ordenamos cronológicamente (antiguo a nuevo) para calcular pares
                        df_calc = df_f.sort_values(by='DT', ascending=True)
                        
                        horas_por_dia = {} # Diccionario: {'2025-01-20': 28800 segundos, ...}
                        ent = None
                        
                        for _, r in df_calc.iterrows():
                            if r['Tipo'] == 'ENTRADA':
                                ent = r['DT']
                            elif r['Tipo'] == 'SALIDA' and ent:
                                delta = (r['DT'] - ent).total_seconds()
                                fecha_clave = ent.strftime("%Y-%m-%d")
                                
                                if fecha_clave in horas_por_dia:
                                    horas_por_dia[fecha_clave] += delta
                                else:
                                    horas_por_dia[fecha_clave] = delta
                                ent = None # Reseteamos par
                        
                        # Crear eventos para el calendario
                        events_audit = []
                        for fecha_iso, segundos in horas_por_dia.items():
                            h_dia = int(segundos // 3600)
                            m_dia = int((segundos % 3600) // 60)
                            
                            texto_evento = f"⏱️ {h_dia}h {m_dia}m"
                            
                            # Color dinámico según horas trabajadas
                            # Rojo si < 5h, Naranja si < 8h, Verde si >= 8h (Ejemplo)
                            if h_dia < 5: color_dia = "#D32F2F" # Poco tiempo
                            elif h_dia < 8: color_dia = "#F57C00" # Jornada incompleta
                            else: color_dia = "#1976D2" # Jornada completa (Azul)

                            events_audit.append({
                                "title": texto_evento,
                                "start": fecha_iso,
                                "end": fecha_iso,
                                "allDay": True,
                                "backgroundColor": color_dia,
                                "borderColor": color_dia,
                                "textColor": "#FFFFFF"
                            })

                        if events_audit:
                            cal_opts_audit = {
                                "editable": False,
                                "height": 600,
                                "initialDate": datetime.now().strftime("%Y-%m-%d"),
                                "headerToolbar": {
                                    "left": "today prev,next",
                                    "center": "title",
                                    "right": "dayGridMonth"
                                },
                                "initialView": "dayGridMonth",
                                "locale": "es",
                                "firstDay": 1
                            }
                            # Clave única
                            key_audit = f"cal_audit_{f_emp}_{len(events_audit)}"
                            calendar(events=events_audit, options=cal_opts_audit, key=key_audit)
                            
                            st.caption("🔵 Jornada Completa (>8h) | 🟠 Jornada Parcial | 🔴 Jornada Reducida (<5h)")
                        else:
                            st.warning("No hay registros de horas completas (Entrada + Salida) para mostrar en este periodo.")

            else:
                st.warning("No hay registros en la base de datos.")
