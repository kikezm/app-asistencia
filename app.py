import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import os
import streamlit_javascript as st_js
import urllib.parse # <--- NUEVA LIBRERÍA PARA ARREGLAR ESPACIOS
import io

# --- CONFIGURACIÓN Y CONEXIÓN A GOOGLE ---
def conectar_google_sheets():
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
    sheet = client.open("Base de Datos Asistencia").sheet1 
    return sheet

# --- FUNCIÓN PARA REGISTRAR ---
def registrar_fichaje(nombre, tipo, info_dispositivo):
    try:
        sheet = conectar_google_sheets()
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M:%S")
        
        sheet.append_row([fecha, hora, nombre, tipo, info_dispositivo])
        
        st.success(f"✅ {tipo} registrada para {nombre}")
        time.sleep(2)
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Error guardando datos: {e}")

# --- INTERFAZ ---
st.set_page_config(page_title="Control Asistencia", page_icon="🕒")

try:
    ua_string = st_js.st_javascript("navigator.userAgent")
except:
    ua_string = "Desconocido"

# Captura el parámetro y arregla los caracteres especiales
params = st.query_params
usuario_url = params.get("empleado", None)

st.title("🕒 Control de Asistencia")

if usuario_url:
    # --- MODO EMPLEADO ---
    st.info(f"👋 Hola, **{usuario_url}**")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🟢 ENTRADA", use_container_width=True):
            registrar_fichaje(usuario_url, "ENTRADA", ua_string)
    with col2:
        if st.button("🔴 SALIDA", use_container_width=True):
            registrar_fichaje(usuario_url, "SALIDA", ua_string)

else:
    # --- MODO ADMIN ---
    menu = ["Panel Admin", "Generador de Enlaces"]
    opcion = st.sidebar.selectbox("Menú", menu)
    
    if opcion == "Generador de Enlaces":
        st.subheader("🔗 Crear enlace seguro")
        nuevo_nombre = st.text_input("Nombre y Apellidos del Empleado")
        
        # --- AQUÍ ES DONDE DEBES PONER TU URL REAL ---
        # Borra la de abajo y pega la tuya:
        MI_URL_REAL = "https://app-asistencia-dknejmfedu4pswfrqf7prc.streamlit.app/" 
        
        if nuevo_nombre:
            # Esto convierte "María Serrano" en "Mar%C3%ADa%20Serrano"
            nombre_seguro = urllib.parse.quote(nuevo_nombre)
            link = f"{MI_URL_REAL}/?empleado={nombre_seguro}"
            
            st.success("Enlace generado correctamente (sin espacios):")
            st.code(link, language="text")
            st.caption("Copia este enlace y envíaselo al trabajador.")







    elif opcion == "Panel Admin":
            st.subheader("🕵️ Gestión de Nóminas y Horas")
            
            password = st.text_input("Contraseña de Acceso", type="password")
            
            if password == "admin123": # <--- TU CONTRASEÑA
                try:
                    sheet = conectar_google_sheets()
                    datos = sheet.get_all_records()
                    
                    if datos:
                        df = pd.DataFrame(datos)
                        
                        # 1. PREPARACIÓN DE DATOS (Crear columnas de fecha reales)
                        # Unimos Fecha y Hora para poder ordenar cronológicamente
                        df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S')
                        df = df.sort_values(by='FechaHora')
                        
                        # Creamos una columna "Mes" para el filtro (Ej: "01/2026")
                        df['Mes_Año'] = df['FechaHora'].dt.strftime('%m/%Y')
                        
                        st.write("---")
                        st.write("### 📅 Configuración del Informe")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # FILTRO 1: Seleccionar MES
                            lista_meses = df['Mes_Año'].unique().tolist()
                            # Ordenamos para que salga el mes más reciente primero
                            lista_meses.sort(reverse=True) 
                            mes_seleccionado = st.selectbox("1. Selecciona el Mes:", lista_meses)
                        
                        # Filtramos el DataFrame solo por ese mes
                        df_mes = df[df['Mes_Año'] == mes_seleccionado].copy()
                        
                        with col2:
                            # FILTRO 2: Seleccionar EMPLEADO (o TODOS)
                            lista_empleados = ["TODOS (Resumen Global)"] + list(df_mes['Empleado'].unique())
                            empleado_selec = st.selectbox("2. Selecciona Empleado:", lista_empleados)
                        
                        # --- LÓGICA DE CÁLCULO ---
                        
                        if st.button(f"📊 Generar Informe de {mes_seleccionado}"):
                            
                            buffer = io.BytesIO()
                            
                            # CASO A: INFORME GLOBAL (TODOS LOS EMPLEADOS)
                            if empleado_selec == "TODOS (Resumen Global)":
                                
                                resumen_global = []
                                empleados_mes = df_mes['Empleado'].unique()
                                
                                for emp in empleados_mes:
                                    # Calculamos horas para cada empleado
                                    df_emp = df_mes[df_mes['Empleado'] == emp].sort_values(by='FechaHora')
                                    segundos_totales = 0
                                    entrada_pendiente = None
                                    
                                    for _, row in df_emp.iterrows():
                                        if row['Tipo'] == 'ENTRADA':
                                            entrada_pendiente = row['FechaHora']
                                        elif row['Tipo'] == 'SALIDA' and entrada_pendiente:
                                            diff = (row['FechaHora'] - entrada_pendiente).total_seconds()
                                            segundos_totales += diff
                                            entrada_pendiente = None
                                    
                                    # Formato horas
                                    horas = int(segundos_totales // 3600)
                                    minutos = int((segundos_totales % 3600) // 60)
                                    
                                    resumen_global.append({
                                        "Empleado": emp,
                                        "Horas Totales": f"{horas}h {minutos}m",
                                        "Segundos": segundos_totales # Oculto para cálculos
                                    })
                                
                                df_global = pd.DataFrame(resumen_global)
                                
                                # Mostrar en pantalla
                                st.write(f"#### Resumen de Horas - {mes_seleccionado}")
                                st.dataframe(df_global[['Empleado', 'Horas Totales']])
                                
                                # Generar Excel Global
                                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                    df_global[['Empleado', 'Horas Totales']].to_excel(writer, sheet_name='Resumen Nómina', index=False)
                                    df_mes[['Fecha', 'Hora', 'Empleado', 'Tipo', 'Dispositivo']].to_excel(writer, sheet_name='Detalle Bruto', index=False)
                                    
                                nombre_archivo = f"Resumen_Global_{mes_seleccionado.replace('/','-')}.xlsx"

                            # CASO B: INFORME INDIVIDUAL (DETALLADO POR DÍA)
                            else:
                                df_emp = df_mes[df_mes['Empleado'] == empleado_selec].sort_values(by='FechaHora')
                                
                                resumen_dias = []
                                dias_unicos = df_emp['Fecha'].unique()
                                total_seconds_mes = 0
                                
                                for dia in dias_unicos:
                                    movs_dia = df_emp[df_emp['Fecha'] == dia]
                                    segs_dia = 0
                                    entrada_pendiente = None
                                    
                                    for _, row in movs_dia.iterrows():
                                        if row['Tipo'] == 'ENTRADA':
                                            entrada_pendiente = row['FechaHora']
                                        elif row['Tipo'] == 'SALIDA' and entrada_pendiente:
                                            diff = (row['FechaHora'] - entrada_pendiente).total_seconds()
                                            segs_dia += diff
                                            entrada_pendiente = None
                                    
                                    h_dia = int(segs_dia // 3600)
                                    m_dia = int((segs_dia % 3600) // 60)
                                    total_seconds_mes += segs_dia
                                    
                                    resumen_dias.append({
                                        "Fecha": dia,
                                        "Horas Trabajadas": f"{h_dia}h {m_dia}m"
                                    })
                                
                                df_individual = pd.DataFrame(resumen_dias)
                                
                                # Totales
                                th = int(total_seconds_mes // 3600)
                                tm = int((total_seconds_mes % 3600) // 60)
                                st.info(f"Total mensual de **{empleado_selec}**: {th}h {tm}m")
                                st.dataframe(df_individual)
                                
                                # Generar Excel Individual
                                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                    df_individual.to_excel(writer, sheet_name='Diario', index=False)
                                    df_emp[['Fecha', 'Hora', 'Tipo', 'Dispositivo']].to_excel(writer, sheet_name='Fichajes', index=False)
                                
                                nombre_archivo = f"Informe_{empleado_selec}_{mes_seleccionado.replace('/','-')}.xlsx"

                            # BOTÓN DE DESCARGA COMÚN
                            buffer.seek(0)
                            st.download_button(
                                label=f"📥 Descargar Excel ({mes_seleccionado})",
                                data=buffer,
                                file_name=nombre_archivo,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )

                    else:
                        st.warning("La base de datos está vacía.")
                except Exception as e:
                    st.error(f"Error: {e}")
