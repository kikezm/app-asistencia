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
    except gspread.SpreadsheetNotFound:
        st.error(f"❌ No encuentro la hoja de cálculo: '{SHEET_NAME}'.")
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

def puede_fichar_hoy(nombre_empleado):
    """Devuelve (True, "") si puede fichar o (False, "Motivo") si está bloqueado"""
    try:
        sheet_cal = conectar_google_sheets("Calendario")
        registros = sheet_cal.get_all_records()
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

        
        # --- SECCIÓN: CALENDARIO INTELIGENTE ---
        if opcion == "Calendario y Festivos":
            st.header("📅 Gestión Masiva de Fechas")
            st.info("Bloquea vacaciones o festivos por rangos de fechas.")
            
            # --- FORMULARIO DE CREACIÓN (Sin cambios) ---
            with st.form("nuevo_bloqueo_masivo"):
                col1, col2 = st.columns(2)
                with col1:
                    fecha_inicio = st.date_input("Fecha Inicio", format="DD/MM/YYYY")
                with col2:
                    fecha_fin = st.date_input("Fecha Fin", value=fecha_inicio, format="DD/MM/YYYY")
                
                if fecha_fin < fecha_inicio:
                    st.error("La fecha de fin no puede ser anterior a la de inicio.")
                
                st.write("---")
                
                col3, col4 = st.columns(2)
                with col3:
                    tipo_bloqueo = st.selectbox("Tipo", ["INDIVIDUAL (Un empleado)", "GLOBAL (Toda la empresa)"])
                    
                    nombre_emp_cal = "TODOS"
                    if "INDIVIDUAL" in tipo_bloqueo:
                        try:
                            sh_u = conectar_google_sheets("Usuarios")
                            lista_nombres = [r['Nombre'] for r in sh_u.get_all_records()]
                            nombre_emp_cal = st.selectbox("Empleado Afectado:", lista_nombres)
                        except:
                            st.error("Error cargando empleados")
                
                with col4:
                    modo_seleccion = st.radio("¿Qué días bloquear?", 
                                              ["Todos los días del rango", "Solo Fines de Semana (Sáb/Dom)"])
                
                motivo = st.text_input("Motivo (Ej: Vacaciones Verano, Cierre Empresa)")
                
                submit_cal = st.form_submit_button("💾 Guardar Fechas en Calendario")
                
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
                                fecha_str = dia_actual.strftime("%d/%m/%Y")
                                filas_a_guardar.append([fecha_str, tipo_str, nombre_emp_cal, motivo])
                        
                        if filas_a_guardar:
                            sheet_cal.append_rows(filas_a_guardar)
                            st.success(f"✅ Se han añadido {len(filas_a_guardar)} días bloqueados al calendario.")
                            time.sleep(1)
                            st.rerun() # Recargamos para que se vea abajo al instante
                        else:
                            st.warning("⚠️ No se seleccionó ningún día.")
                            
                    except Exception as e:
                        st.error(f"Error guardando: {e}")

            st.write("---")
            
            # --- ZONA DE EDICIÓN MEJORADA ---
            with st.expander("📂 Ver y Modificar Fechas Bloqueadas (Clic para desplegar)"):
                try:
                    sheet_cal = conectar_google_sheets("Calendario")
                    data_cal = sheet_cal.get_all_records()
                    
                    if data_cal:
                        df_cal = pd.DataFrame(data_cal)
                        
                        # 1. ORDENAMOS VISUALMENTE ANTES DE MOSTRAR
                        # Convertimos a fecha real para ordenar correctamente (no alfabéticamente)
                        df_cal['Fecha_Orden'] = pd.to_datetime(df_cal['Fecha'], format='%d/%m/%Y', errors='coerce')
                        df_cal = df_cal.sort_values(by='Fecha_Orden', ascending=False) # Las fechas futuras arriba
                        
                        # Guardamos el índice original implícitamente al manipular el DF
                        # Eliminamos la columna auxiliar visual para que no moleste en el editor
                        df_editor_view = df_cal.drop(columns=['Fecha_Orden'])
                        
                        st.info("🗑️ Para borrar: Selecciona la fila (clic a la izquierda) y pulsa 'Supr'. Luego dale a Guardar.")
                        
                        # EDITOR
                        edited_df = st.data_editor(
                            df_editor_view, 
                            num_rows="dynamic", 
                            use_container_width=True,
                            key="editor_calendario",
                            hide_index=True # Ocultamos el índice numérico feo (0, 1, 2...)
                        )
                        
                        # BOTÓN DE GUARDADO INTELIGENTE
                        if st.button("💾 Guardar Cambios y Reordenar"):
                            try:
                                # AQUI ESTÁ LA MAGIA:
                                # 1. Cogemos lo que el usuario ha modificado (puede estar desordenado)
                                df_final = edited_df.copy()
                                
                                # 2. Convertimos la fecha a real OTRA VEZ para asegurar el orden en el archivo
                                df_final['Aux_Sort'] = pd.to_datetime(df_final['Fecha'], format='%d/%m/%Y', errors='coerce')
                                
                                # 3. Borramos filas donde la fecha sea inválida (por si el usuario borró la fecha por error)
                                df_final = df_final.dropna(subset=['Aux_Sort'])
                                
                                # 4. ORDENAMOS LA TABLA FINAL (Cronológico descendente)
                                df_final = df_final.sort_values(by='Aux_Sort', ascending=False)
                                
                                # 5. Quitamos la columna auxiliar
                                df_final = df_final.drop(columns=['Aux_Sort'])
                                
                                # 6. Preparamos para subir a Google Sheets
                                nuevos_datos = [df_final.columns.values.tolist()] + df_final.values.tolist()
                                
                                sheet_cal.clear()
                                sheet_cal.update(nuevos_datos)
                                
                                st.success("✅ Calendario actualizado y reordenado correctamente.")
                                time.sleep(1)
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Error al procesar los datos: {e}")
                            
                    else:
                        st.info("El calendario está vacío.")
                except Exception as e:
                    st.warning(f"Error cargando calendario: {e}")

        # --- SECCIÓN: USUARIOS (Igual) ---
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
                    except Exception as e: st.error(f"Error: {e}")

        # --- SECCIÓN: AUDITORÍA (Igual) ---
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





