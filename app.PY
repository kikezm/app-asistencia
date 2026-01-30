import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time



# --- CONFIGURACIÓN Y CONEXIÓN A GOOGLE ---
def conectar_google_sheets():
    # Definimos el alcance
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    # INTENTAMOS LEER DE LA NUBE (STREAMLIT SECRETS)
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    # SI FALLA, LEEMOS DEL ARCHIVO LOCAL (TU PC)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    
    client = gspread.authorize(creds)
    
    # Abrimos la hoja
    sheet = client.open("Base de Datos Asistencia").sheet1 
    return sheet




# --- FUNCIÓN PARA REGISTRAR ---
def registrar_fichaje(nombre, tipo):
    try:
        sheet = conectar_google_sheets()
        
        ahora = datetime.now()
        fecha = ahora.strftime("%d/%m/%Y")
        hora = ahora.strftime("%H:%M:%S")
        
        # Añadimos la fila a Google Sheets
        sheet.append_row([fecha, hora, nombre, tipo])
        
        st.success(f"✅ ¡Hecho! {tipo} registrada para {nombre} a las {hora}")
        time.sleep(2) # Pausa pequeña para que se lea el mensaje
        st.rerun() # Recargamos la página para limpiar
        
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")

# --- INTERFAZ DE LA APLICACIÓN ---
st.set_page_config(page_title="Control Asistencia", page_icon="🕒")

st.title("🕒 Control de Asistencia")

menu = ["Fichar", "Administración (Informes)"]
opcion = st.sidebar.selectbox("Ir a:", menu)

if opcion == "Fichar":
    st.subheader("Registro de Jornada")
    
    # Lista de empleados (Puedes editar esta lista)
    lista_empleados = ["Selecciona tu nombre...", "Juan Pérez", "María García", "Carlos López"]
    nombre = st.selectbox("Empleado:", lista_empleados)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🟢 ENTRADA", use_container_width=True):
            if nombre != "Selecciona tu nombre...":
                registrar_fichaje(nombre, "ENTRADA")
            else:
                st.warning("Por favor, selecciona tu nombre.")
                
    with col2:
        if st.button("🔴 SALIDA", use_container_width=True):
            if nombre != "Selecciona tu nombre...":
                registrar_fichaje(nombre, "SALIDA")
            else:
                st.warning("Por favor, selecciona tu nombre.")

elif opcion == "Administración (Informes)":
    st.subheader("Panel de Gestión")
    
    # Contraseña simple para que no entre cualquiera (puedes cambiarla)
    password = st.text_input("Contraseña de Administrador", type="password")
    
    if password == "admin123": # CAMBIA ESTO POR TU CONTRASEÑA
        try:
            sheet = conectar_google_sheets()
            datos = sheet.get_all_records()
            
            if datos:
                df = pd.DataFrame(datos)
                st.write("### Últimos movimientos")
                st.dataframe(df.tail(10)) # Muestra los últimos 10
                
                # --- GENERADOR DE INFORMES ---
                st.write("---")
                st.write("### Descargar Informe")
                
                empleado_filtro = st.selectbox("Filtrar por empleado (opcional):", 
                                             ["Todos"] + list(df['Empleado'].unique()))
                
                if empleado_filtro != "Todos":
                    df_final = df[df['Empleado'] == empleado_filtro]
                else:
                    df_final = df
                
                # Botón de descarga CSV
                csv = df_final.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Informe (CSV/Excel)",
                    data=csv,
                    file_name=f'informe_asistencia_{datetime.now().strftime("%Y%m%d")}.csv',
                    mime='text/csv',
                )
            else:
                st.info("La base de datos está vacía.")
                
        except Exception as e:
            st.error(f"Error cargando datos: {e}")