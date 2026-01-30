import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import os
import streamlit_javascript as st_js
import urllib.parse # <--- NUEVA LIBRERÍA PARA ARREGLAR ESPACIOS

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
            st.subheader("🕵️ Panel de Control y Nóminas")
            
            # --- CAMBIA TU CONTRASEÑA AQUÍ ---
            password = st.text_input("Contraseña de Acceso", type="password")
            
            if password == "admin123": # <--- Pon aquí tu contraseña
                try:
                    sheet = conectar_google_sheets()
                    datos = sheet.get_all_records()
                    
                    if datos:
                        df = pd.DataFrame(datos)
                        
                        # Convertimos las columnas de fecha y hora a formato que Python entienda
                        # Creamos una columna temporal "FechaHora" para ordenar
                        df['FechaHora'] = pd.to_datetime(df['Fecha'] + ' ' + df['Hora'], format='%d/%m/%Y %H:%M:%S')
                        df = df.sort_values(by='FechaHora') # Ordenamos cronológicamente
                        
                        st.write("---")
                        st.write("### 📊 Generar Informe de Horas")
                        
                        # 1. Seleccionar Empleado
                        lista_empleados = list(df['Empleado'].unique())
                        empleado_selec = st.selectbox("Selecciona Empleado para calcular horas:", lista_empleados)
                        
                        if empleado_selec:
                            # Filtramos solo los datos de ese empleado
                            df_emp = df[df['Empleado'] == empleado_selec].copy()
                            
                            # --- ALGORITMO DE CÁLCULO DE HORAS ---
                            resumen_data = []
                            entrada_temp = None
                            
                            # Agrupamos por día
                            dias_unicos = df_emp['Fecha'].unique()
                            
                            total_horas_periodo = 0
                            
                            for dia in dias_unicos:
                                # Filtramos los movimientos de ESE día
                                movimientos_dia = df_emp[df_emp['Fecha'] == dia].sort_values(by='FechaHora')
                                
                                segundos_trabajados_dia = 0
                                entrada_pendiente = None
                                
                                for index, row in movimientos_dia.iterrows():
                                    if row['Tipo'] == 'ENTRADA':
                                        entrada_pendiente = row['FechaHora']
                                    
                                    elif row['Tipo'] == 'SALIDA' and entrada_pendiente is not None:
                                        # Calculamos la diferencia
                                        diferencia = row['FechaHora'] - entrada_pendiente
                                        segundos = diferencia.total_seconds()
                                        segundos_trabajados_dia += segundos
                                        entrada_pendiente = None # Reseteamos para el siguiente turno (si hay pausa comida)
                                
                                # Convertir segundos a Horas:Minutos
                                horas = int(segundos_trabajados_dia // 3600)
                                minutos = int((segundos_trabajados_dia % 3600) // 60)
                                texto_tiempo = f"{horas}h {minutos}m"
                                
                                total_horas_periodo += segundos_trabajados_dia
                                
                                resumen_data.append({
                                    "Fecha": dia,
                                    "Horas Trabajadas": texto_tiempo,
                                    "Segundos (Cálculo)": segundos_trabajados_dia # Oculto, para excel
                                })
                            
                            # Crear DataFrame del Resumen
                            df_resumen = pd.DataFrame(resumen_data)
                            
                            # Mostrar métricas en pantalla
                            horas_totales = int(total_horas_periodo // 3600)
                            minutos_totales = int((total_horas_periodo % 3600) // 60)
                            
                            st.info(f"📅 Resumen para **{empleado_selec}**")
                            st.metric("Total Horas Acumuladas", f"{horas_totales}h {minutos_totales}m")
                            
                            st.table(df_resumen[['Fecha', 'Horas Trabajadas']])
                            
                            # Botón Descargar Resumen
                            csv_resumen = df_resumen.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label=f"📥 Descargar Resumen de {empleado_selec}",
                                data=csv_resumen,
                                file_name=f"Resumen_Horas_{empleado_selec}.csv",
                                mime="text/csv"
                            )
                            
                            # Opción de ver datos crudos
                            with st.expander("Ver fichajes detallados (Raw Data)"):
                                st.dataframe(df_emp[['Fecha', 'Hora', 'Tipo', 'Dispositivo']])
    
                    else:
                        st.warning("La base de datos está vacía.")
                except Exception as e:
                    st.error(f"Error calculando datos: {e}")
