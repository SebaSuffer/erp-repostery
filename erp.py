import streamlit as st
try:
    from supabase import create_client, Client
except ImportError:
    from supabase import create_client
import pandas as pd
import time
import json 
import altair as alt
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="TV Repostería ERP",
    layout="wide",
    page_icon="🧁",
    initial_sidebar_state="expanded"
)


# --- ESTILOS CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: #1c120d;
    }
    .login-container {
        display: flex; justify-content: center; align-items: center; margin-top: 50px;
    }
    
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #f4ebe7; }
    .stButton>button {
        background-color: #f2590d; color: white; border-radius: 12px; font-weight: 600; border: none;
        padding: 0.5rem 1rem; box-shadow: 0 4px 6px -1px rgba(242, 89, 13, 0.2); transition: all 0.2s;
    }
    .stButton>button:hover { background-color: #d94a05; transform: translateY(-1px); }
    div[data-testid="column"] button {
        background-color: #ffffff; color: #9c6549; border: 1px solid #f4ebe7; box-shadow: none;
    }
    div[data-testid="column"] button:hover {
        background-color: #f8f6f5; color: #f2590d; border-color: #f2590d;
    }
    .kanban-card {
        background-color: #ffffff; border: 1px solid #f4ebe7; border-radius: 16px; padding: 20px;
        margin-bottom: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .badge { display: inline-block; padding: 4px 8px; border-radius: 8px; font-size: 12px; font-weight: 700; }
    .badge-blue { background-color: #dbeafe; color: #1e40af; }
    .badge-yellow { background-color: #fef9c3; color: #854d0e; }
    .badge-green { background-color: #dcfce7; color: #166534; }
    .badge-gray { background-color: #f3f4f6; color: #374151; }
    div[data-testid="stMetric"] {
        background-color: #fff; border: 1px solid #f4ebe7; padding: 15px; border-radius: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.02);
    }
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        # ¡ESTO MOSTRARÁ LA CAUSA REAL DEL FALLO EN LA PANTALLA!
        st.error(f"¡ERROR FATAL DE CONEXIÓN! Detalle: {e}") 
        return None

supabase = init_connection()

# --- GESTIÓN DE SESIÓN ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'usuario_actual' not in st.session_state:
    st.session_state.usuario_actual = None
if 'rol_actual' not in st.session_state:
    st.session_state.rol_actual = None

# --- LÓGICA DE NEGOCIO ---

def registrar_gasto(monto, descripcion, fecha=None):
    """Registra una compra de insumos en el libro financiero."""
    if not fecha: fecha = str(datetime.now().date())
    if supabase:
        try:
            supabase.table('gastos').insert({
                "fecha": fecha, "monto": monto, "descripcion": descripcion, "tipo": "Compra Insumo"
            }).execute()
            return True
        except Exception as e:
            st.error(f"Error registrando gasto: {e}")
            return False

def descontar_stock_automatico(pedido):
    """Resta stock al entregar."""
    if not supabase: return []
    try:
        if not pedido.get('detalle_json'): return []
        detalle = json.loads(pedido['detalle_json'])
        log = []
        insumos_db = supabase.table('insumos').select("*").execute().data
        insumos_map = {i['nombre']: i for i in insumos_db}
        
        for item in detalle:
            nombre_prod = item['producto']
            cant_vendida = item['cantidad']
            receta = supabase.table('recetas').select("ingredientes_json").eq('nombre', nombre_prod).execute().data
            
            if receta and receta[0]['ingredientes_json']:
                ings = json.loads(receta[0]['ingredientes_json'])
                for ing in ings:
                    nombre_ing = ing['nombre']
                    cant_ing_unitaria = ing['cantidad']
                    total_desc = cant_ing_unitaria * cant_vendida
                    if nombre_ing in insumos_map:
                        stock_actual = insumos_map[nombre_ing]['stock_actual']
                        nuevo = stock_actual - total_desc
                        supabase.table('insumos').update({"stock_actual": nuevo}).eq('nombre', nombre_ing).execute()
                        log.append(f"- {nombre_ing}: {stock_actual} → {nuevo}")
        return log
    except Exception as e:
        print(f"Error descontando stock: {e}")
        return []

def reponer_stock_automatico(pedido):
    """Devuelve stock al cancelar una entrega (Devolución)."""
    if not supabase: return []
    try:
        if not pedido.get('detalle_json'): return []
        detalle = json.loads(pedido['detalle_json'])
        log = []
        insumos_db = supabase.table('insumos').select("*").execute().data
        insumos_map = {i['nombre']: i for i in insumos_db}
        
        for item in detalle:
            nombre_prod = item['producto']
            cant_vendida = item['cantidad']
            receta = supabase.table('recetas').select("ingredientes_json").eq('nombre', nombre_prod).execute().data
            
            if receta and receta[0]['ingredientes_json']:
                ings = json.loads(receta[0]['ingredientes_json'])
                for ing in ings:
                    nombre_ing = ing['nombre']
                    total_reponer = ing['cantidad'] * cant_vendida
                    if nombre_ing in insumos_map:
                        stock_actual = insumos_map[nombre_ing]['stock_actual']
                        nuevo = stock_actual + total_reponer
                        supabase.table('insumos').update({"stock_actual": nuevo}).eq('nombre', nombre_ing).execute()
                        log.append(f"⬆️ {nombre_ing}: {stock_actual} → {nuevo}")
        return log
    except Exception as e:
        print(f"Error reponiendo stock: {e}")
        return []

def cambiar_estado_pedido(id_pedido, nuevo_estado, datos_pedido=None):
    if supabase:
        supabase.table('pedidos').update({'estado': nuevo_estado}).eq('id', id_pedido).execute()
        
        msg = ""
        # Lógica de Stock Completa (Entrada y Salida)
        if nuevo_estado == "Entregado" and datos_pedido:
            log = descontar_stock_automatico(datos_pedido)
            if log: msg = " | 📉 Stock descontado"
            
        elif nuevo_estado == "Cancelado":
            # Si estaba entregado y se cancela -> Devolución
            if datos_pedido and datos_pedido['estado'] == 'Entregado':
                log = reponer_stock_automatico(datos_pedido)
                if log: msg = " | 🔄 Stock devuelto"
            else:
                msg = " | Pedido cerrado"

        st.toast(f"Estado: {nuevo_estado}{msg}", icon="✅")
        time.sleep(1)
        st.rerun()

# --- PANTALLA DE LOGIN ---
def login_screen():
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.image("https://i.postimg.cc/fy8vC6RP/172582480-314301286701036-2832058173383995414-n-waifu2x-art-noise1-scale.png", width=150)
        st.markdown("<h2 style='text-align: center; color: #1c120d;'>TV Repostería</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #9c6549;'>Sistema ERP v6.1</p>", unsafe_allow_html=True)
        
        with st.form("login"):
            user = st.text_input("Usuario")
            pwd = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Ingresar", use_container_width=True):
                if supabase:
                    res = supabase.table('usuarios').select("*").eq('username', user).eq('password', pwd).execute()
                    if res.data:
                        st.session_state.authenticated = True
                        st.session_state.usuario_actual = res.data[0]['nombre']
                        st.session_state.rol_actual = res.data[0]['rol']
                        st.success("¡Bienvenido!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Credenciales incorrectas")
                else:
                    st.error("Error de conexión DB")

# --- APLICACIÓN PRINCIPAL ---
def main_app():
    # Sidebar
    with st.sidebar:
        st.markdown(f"""
            <div style="text-align: center; padding-bottom: 20px;">
                <img src="https://i.postimg.cc/fy8vC6RP/172582480-314301286701036-2832058173383995414-n-waifu2x-art-noise1-scale.png" 
                     style="width: 100px; border-radius: 50%; border: 4px solid #f2590d; padding: 2px;">
                <h2 style="margin-top: 10px; font-size: 18px;">TV Repostería</h2>
                <p style="color: #9c6549; font-size: 12px;">ERP v6.1 Full Stack</p>
            </div>
        """, unsafe_allow_html=True)
        
        menu = st.radio("", ["📊 Finanzas & Dashboard", "📌 Pedidos", "🧁 Mis Productos", "📦 Inventario", "⚙️ Configuración"])
        st.divider()
        
        # Usuario actual
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 10px; padding: 10px; background: #f8f6f5; border-radius: 12px;">
            <div style="width: 35px; height: 35px; background: #f2590d; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 14px;">
                {st.session_state.usuario_actual[0].upper()}
            </div>
            <div>
                <div style="font-weight: 700; font-size: 14px;">{st.session_state.usuario_actual}</div>
                <div style="font-size: 12px; color: #9c6549;">{st.session_state.rol_actual}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.usuario_actual = None
            st.session_state.rol_actual = None
            st.rerun()

    # ==========================================
    # 📊 FINANZAS
    # ==========================================
    if menu == "📊 Finanzas & Dashboard":
        st.title("Estado Financiero del Negocio")
        st.markdown('<p style="color: #666; margin-top: -10px;">Balance real entre Ventas (Ingresos) y Compras (Egresos).</p>', unsafe_allow_html=True)

        ventas_tot = 0
        gastos_tot = 0
        df_v = pd.DataFrame()
        df_g = pd.DataFrame()

        if supabase:
            # Ventas
            try:
                pr = supabase.table('pedidos').select("fecha_entrega, total_pedido, estado").execute().data
                if pr:
                    dfp = pd.DataFrame(pr)
                    if 'total_pedido' in dfp.columns and not dfp.empty:
                        ventas_tot = dfp[dfp['estado'] == 'Entregado']['total_pedido'].sum()
                        dfp['fecha'] = pd.to_datetime(dfp['fecha_entrega'])
                        dfp['tipo'] = 'Venta'
                        dfp = dfp.rename(columns={'total_pedido': 'monto'})
                        df_v = dfp[dfp['estado'] == 'Entregado'][['fecha', 'monto', 'tipo']]
            except: pass
            
            # Gastos
            try:
                gr = supabase.table('gastos').select("*").execute().data
                if gr:
                    dfg = pd.DataFrame(gr)
                    if 'monto' in dfg.columns:
                        gastos_tot = dfg['monto'].sum()
                        dfg['fecha'] = pd.to_datetime(dfg['fecha'])
                        dfg['tipo'] = 'Gasto'
                        df_g = dfg[['fecha', 'monto', 'tipo']]
            except: pass

        balance = ventas_tot - gastos_tot
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Totales (Ventas)", f"${ventas_tot:,.0f}", help="Solo pedidos entregados")
        c2.metric("Egresos Totales (Compras)", f"${gastos_tot:,.0f}", help="Compras registradas")
        c3.metric("Balance Neto (Ganancia)", f"${balance:,.0f}", delta="Rentable" if balance > 0 else "Pérdida")

        st.write("")
        st.subheader("📈 Evolución Mensual")
        
        if not df_v.empty or not df_g.empty:
            df_full = pd.concat([df_v, df_g])
            df_full['Mes'] = df_full['fecha'].dt.strftime('%Y-%m')
            chart_data = df_full.groupby(['Mes', 'tipo'])['monto'].sum().reset_index()
            
            chart = alt.Chart(chart_data).mark_bar().encode(
                x='Mes',
                y='monto',
                color=alt.Color('tipo', scale=alt.Scale(domain=['Venta', 'Gasto'], range=['#22c55e', '#ef4444'])),
                tooltip=['Mes', 'tipo', 'monto']
            ).interactive()
            
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Aún no hay suficientes movimientos para generar gráficos.")

    # ==========================================
    # 🛒 PEDIDOS (V5: FUNCIONAL CON NUEVA BD)
    # ==========================================
    elif menu == "🛒 Pedidos" or menu == "📌 Pedidos": # Aceptamos ambos nombres por si acaso
        st.title("🛒 Gestión de Pedidos")

        # 1. Cargar Datos del Catálogo
        mapa_productos_base = {}
        todas_variaciones = []
        lista_bases_nombres = []
        
        if supabase:
            try:
                # Cargar Bases
                data_p = supabase.table('productos').select("*").order('nombre').execute().data
                if data_p:
                    mapa_productos_base = {p['nombre']: p for p in data_p}
                    lista_bases_nombres = list(mapa_productos_base.keys())

                # Cargar Variaciones (Hijos)
                todas_variaciones = supabase.table('variaciones').select("*").execute().data
            except Exception as e:
                st.error(f"Error conectando al catálogo: {e}")

        tab_nuevo, tab_tablero = st.tabs(["➕ Nuevo Pedido", "📋 Tablero de Cocina"])

        # --- TAB: NUEVO PEDIDO ---
        with tab_nuevo:
            st.subheader("Ingresar Orden de Cliente")
            
            if not lista_bases_nombres:
                st.warning("⚠️ El catálogo está vacío. Ve a 'Mis Productos' para crear tortas primero.")
            else:
                col_cliente, col_prod = st.columns([1, 2])
                
                with col_cliente:
                    st.markdown("##### 👤 Cliente")
                    cliente_nombre = st.text_input("Nombre Cliente", key="cli_nom")
                    cliente_contacto = st.text_input("Teléfono / WhatsApp", key="cli_tel")
                    
                    st.markdown("##### 📅 Entrega")
                    fecha_entrega = st.date_input("Fecha Comprometida")
                    hora_entrega = st.time_input("Hora Aprox")

                with col_prod:
                    st.markdown("##### 🎂 Selección de Producto")
                    
                    # 1. Selector de BASE (Masa)
                    base_selec = st.selectbox("1. Tipo de Masa / Base", lista_bases_nombres, index=None, key="new_base_sel", placeholder="Selecciona masa...")
                    
                    variacion_data = None
                    precio_sugerido = 0

                    if base_selec:
                        id_base = mapa_productos_base[base_selec]['id']
                        # Filtrar hijos que pertenezcan a esta base
                        vars_filtradas = [v for v in todas_variaciones if v['producto_id'] == id_base]
                        
                        if not vars_filtradas:
                            st.warning(f"La '{base_selec}' no tiene tamaños ni sabores creados. Edítala en el Catálogo.")
                        else:
                            # Crear mapa
                            mapa_vars = {v['nombre']: v for v in vars_filtradas}
                            
                            # 2. Selector de VARIACIÓN (Sabor y Tamaño)
                            var_selec_nombre = st.selectbox("2. Sabor y Tamaño", list(mapa_vars.keys()), index=None, key="new_var_sel", placeholder="Elige variedad...")
                            
                            if var_selec_nombre:
                                variacion_data = mapa_vars[var_selec_nombre]
                                precio_sugerido = variacion_data['precio']
                                st.success(f"✅ Seleccionado: **{base_selec}** | **{var_selec_nombre}**")

                    st.divider()
                    
                    c_cant, c_precio = st.columns(2)
                    cantidad = c_cant.number_input("Cantidad", 1, 50, 1)
                    precio_final = c_precio.number_input("Precio Final Unitario ($)", value=int(precio_sugerido), step=500)
                    
                    total_calc = cantidad * precio_final
                    st.markdown(f"<h2 style='text-align:right; color:#f2590d'>Total: ${total_calc:,.0f}</h2>", unsafe_allow_html=True)
                    
                    notas = st.text_area("📝 Notas Especiales (Dedicatoria, Alergias, Diseño)")

                    if st.button("💾 Confirmar Pedido", type="primary", use_container_width=True):
                        if cliente_nombre and variacion_data:
                            try:
                                datos = {
                                    "cliente_nombre": cliente_nombre,
                                    "cliente_contacto": cliente_contacto,
                                    "fecha_entrega": str(fecha_entrega),
                                    "hora_entrega": str(hora_entrega),
                                    "variacion_id": variacion_data['id'],
                                    "nombre_producto_snapshot": f"{base_selec} - {variacion_data['nombre']}",
                                    "cantidad": cantidad,
                                    "precio_unitario_final": precio_final,
                                    "total_pedido": total_calc,
                                    "estado": "Pendiente",
                                    "notas": notas
                                }
                                supabase.table('pedidos').insert(datos).execute()
                                st.balloons()
                                st.success("¡Pedido enviado a cocina!")
                                time.sleep(1.5)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error guardando: {e}")
                        else:
                            st.error("Faltan datos del cliente o seleccionar producto.")

        # --- TAB: KANBAN ---
        with tab_tablero:
            st.subheader("📋 Tablero de Producción")
            
            # Cargar pedidos activos
            pedidos_activos = []
            if supabase:
                try:
                    # Traemos todo lo que no esté Cancelado ni Entregado (histórico)
                    pedidos_activos = supabase.table('pedidos').select("*").neq('estado', 'Cancelado').neq('estado', 'Entregado').order('fecha_entrega').execute().data
                except: pass
            
            if not pedidos_activos:
                st.info("🎉 No hay pedidos pendientes. ¡Todo al día!")
            else:
                for p in pedidos_activos:
                    # Tarjeta de Pedido
                    with st.container():
                        st.markdown(f"""
                        <div class="kanban-card">
                            <div style="display:flex; justify-content:space-between;">
                                <span>🆔 <b>#{p['id']}</b></span>
                                <span>📅 <b>{p['fecha_entrega']}</b></span>
                            </div>
                            <h4 style="margin:5px 0">{p['cliente_nombre']}</h4>
                            <p style="color:#666">🍰 {p['nombre_producto_snapshot']} (x{p['cantidad']})</p>
                            <p><i>Nota: {p.get('notas') or 'Sin notas'}</i></p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        col_state, col_btns = st.columns([2, 3])
                        
                        with col_state:
                            st.caption("Estado Actual:")
                            if p['estado'] == 'Pendiente': st.warning("🟡 Pendiente")
                            elif p['estado'] == 'En Horno': st.info("🔵 En Horno")
                            elif p['estado'] == 'Listo': st.success("🟢 Listo para Retiro")
                        
                        with col_btns:
                            st.caption("Acciones:")
                            c_b1, c_b2, c_b3 = st.columns(3)
                            
                            # Lógica de Botones según estado
                            if p['estado'] == 'Pendiente':
                                if c_b1.button("🔥 Horno", key=f"h_{p['id']}"):
                                    supabase.table('pedidos').update({'estado': 'En Horno'}).eq('id', p['id']).execute()
                                    st.rerun()
                            
                            if p['estado'] == 'En Horno':
                                if c_b2.button("✅ Listo", key=f"l_{p['id']}"):
                                    supabase.table('pedidos').update({'estado': 'Listo'}).eq('id', p['id']).execute()
                                    st.rerun()
                                    
                            if p['estado'] == 'Listo':
                                if c_b3.button("🚚 Entregar", key=f"e_{p['id']}"):
                                    supabase.table('pedidos').update({'estado': 'Entregado'}).eq('id', p['id']).execute()
                                    # Registrar Venta en Gastos (Ingreso positivo)
                                    registrar_gasto(p['total_pedido'] * 1, f"Venta Pedido #{p['id']} - {p['cliente_nombre']}")
                                    st.toast("¡Pedido Entregado y Venta Registrada!")
                                    time.sleep(1.5)
                                    st.rerun()
                            
                            # Botón cancelar siempre disponible
                            if st.button("❌ Cancelar", key=f"c_{p['id']}"):
                                supabase.table('pedidos').update({'estado': 'Cancelado'}).eq('id', p['id']).execute()
                                st.rerun()
                        st.divider()

    # ==========================================
    # 🧁 PRODUCTOS Y VARIACIONES (V11: DECIMALES LIMPIOS)
    # ==========================================
    elif menu == "🧁 Mis Productos":
        st.title("🧁 Catálogo Maestro")
        st.markdown("Gestiona tus masas base y crea sus variaciones con calculadora de costos avanzada.")

        # --- HELPER: Conversión para Recetas ---
        def convertir_a_base(cantidad, unidad_receta, unidad_inventario):
            if unidad_receta == unidad_inventario: return cantidad
            factor_cdta = 5
            factor_cda = 15

            if unidad_inventario == 'kg':
                if unidad_receta == 'gr': return cantidad / 1000
                if unidad_receta == 'cdta': return (cantidad * factor_cdta) / 1000 
                if unidad_receta == 'cda': return (cantidad * factor_cda) / 1000
            
            if unidad_inventario == 'gr':
                if unidad_receta == 'kg': return cantidad * 1000
                if unidad_receta == 'cdta': return cantidad * factor_cdta
                if unidad_receta == 'cda': return cantidad * factor_cda
            
            if unidad_inventario == 'lt':
                if unidad_receta in ['ml', 'cc']: return cantidad / 1000
                if unidad_receta == 'cdta': return (cantidad * factor_cdta) / 1000
                if unidad_receta == 'cda': return (cantidad * factor_cda) / 1000
            
            if unidad_inventario in ['ml', 'cc']:
                if unidad_receta == 'lt': return cantidad * 1000
                if unidad_receta == 'cdta': return cantidad * factor_cdta
                if unidad_receta == 'cda': return cantidad * factor_cda
            return 0 

        def calcular_precio_final(costo_insumos, p_merma, p_ops, costo_mo, p_maq, p_margen, costo_empaque):
            val_merma = costo_insumos * (p_merma / 100)
            sub1 = costo_insumos + val_merma
            val_ops = sub1 * (p_ops / 100)
            sub2 = sub1 + val_ops
            sub3 = sub2 + costo_mo
            val_maq = sub3 * (p_maq / 100)
            sub4 = sub3 + val_maq
            val_ganancia = sub4 * (p_margen / 100)
            sub5 = sub4 + val_ganancia
            final = sub5 + costo_empaque
            
            return final, {
                "insumos": costo_insumos, "merma": val_merma, "ops": val_ops,
                "mo": costo_mo, "maq": val_maq, "ganancia": val_ganancia, "empaque": costo_empaque
            }
        
        def mostrar_cantidad(valor):
            if valor == int(valor): return str(int(valor))
            return f"{valor:.2f}".rstrip('0').rstrip('.')

        # Cargar Datos
        mapa_insumos = {}
        lista_productos_base = []
        mapa_productos_base = {}

        if supabase:
            try:
                data_i = supabase.table('insumos').select("*").order('nombre').execute().data
                mapa_insumos = {i['nombre']: i for i in data_i}
                data_p = supabase.table('productos').select("*").order('nombre').execute().data
                lista_productos_base = [p['nombre'] for p in data_p]
                mapa_productos_base = {p['nombre']: p for p in data_p}
            except: pass
        
        tab_catalogo, tab_base, tab_variacion, tab_editor = st.tabs(["📖 Ver Catálogo", "✨ 1. Crear Masa Base", "🍰 2. Crear Variación", "✏️ Editor de Recetas"])
        
        with tab_editor:
            st.subheader("✏️ Editor de Recetas")
            if 'edit_var_id' not in st.session_state: st.session_state.edit_var_id = None
                
            if st.session_state.edit_var_id is None:
                st.info("👈 Ve a la pestaña 'Ver Catálogo' y presiona el botón '✏️ Editar Receta'.")
            else:
                var_data = st.session_state.edit_var_data
                st.markdown(f"Editando: **{var_data['nombre']}**")
                
                col_e1, col_e2 = st.columns([1, 1.2])
                
                with col_e1:
                    st.markdown("##### 🥣 Ingredientes")
                    insumo_k = st.selectbox("Agregar Insumo", list(mapa_insumos.keys()), index=None, key="edit_sel_ins")
                    if insumo_k:
                        d_ins = mapa_insumos[insumo_k]
                        u_base = d_ins['unidad_medida']
                        cc1, cc2 = st.columns(2)
                        v_cant = cc1.number_input("Cant.", min_value=0.0, value=1.0, format="%.2f", step=0.1, key="edit_cant")
                        
                        opts = [u_base]
                        if u_base == 'kg': opts = ['gr', 'kg', 'cdta', 'cda']
                        elif u_base == 'gr': opts = ['gr', 'kg', 'cdta', 'cda']
                        elif u_base == 'lt': opts = ['ml', 'lt', 'cc', 'cdta', 'cda']
                        elif u_base in ['ml', 'cc']: opts = ['ml', 'lt', 'cc', 'cdta', 'cda']
                        v_uni = cc2.selectbox("Unidad", opts, key="edit_uni")
                        
                        if st.button("➕ Añadir", key="edit_add_btn"):
                            if v_cant > 0:
                                cant_norm = convertir_a_base(v_cant, v_uni, u_base)
                                costo_linea = cant_norm * d_ins['costo_unitario']
                                st.session_state.edit_ingredientes.append({
                                    "nombre": insumo_k, "cantidad": v_cant, "unidad": v_uni, 
                                    "costo": costo_linea, "insumo_id": d_ins['id']
                                })
                                st.rerun()
                    
                    st.divider()
                    st.caption("Lista de Ingredientes:")
                    total_receta_edit = 0
                    for idx, ing in enumerate(st.session_state.edit_ingredientes):
                        costo_actual = ing['costo']
                        if ing['nombre'] in mapa_insumos:
                            d_actual = mapa_insumos[ing['nombre']]
                            cant_norm = convertir_a_base(ing['cantidad'], ing['unidad'], d_actual['unidad_medida'])
                            costo_actual = cant_norm * d_actual['costo_unitario']
                        ing['costo'] = costo_actual
                        total_receta_edit += costo_actual
                        
                        c_txt, c_btn = st.columns([4, 1])
                        cant_display = mostrar_cantidad(ing['cantidad'])
                        c_txt.markdown(f"**• {cant_display} {ing['unidad']} {ing['nombre']}** (${costo_actual:,.0f})")
                        if c_btn.button("🗑️", key=f"del_edit_{idx}"):
                            st.session_state.edit_ingredientes.pop(idx)
                            st.rerun()

                with col_e2:
                    st.markdown("##### 💰 Estructura de Costos")
                    st.info(f"Costo Ingredientes Base: **${total_receta_edit:,.0f}**")
                    
                    with st.expander("⚙️ Configuración Avanzada de Costos", expanded=True):
                        ep1, ep2 = st.columns(2)
                        p_merma = ep1.slider("Merma (%)", 0, 15, 5, key="ed_merma")
                        p_ops = ep2.slider("Gastos Ops (%)", 0, 30, 15, key="ed_ops")
                        ep3, ep4 = st.columns(2)
                        costo_mo = ep3.number_input("Mano de Obra ($)", value=6400, step=1000, key="ed_mo")
                        p_maq = ep4.slider("Mantención Maq. (%)", 0, 20, 5, key="ed_maq")
                        st.divider()
                        p_margen = st.slider("Margen Ganancia (%)", 10, 100, 60, key="ed_margen")
                        costo_empaque = st.number_input("Costo Empaque ($)", value=3000, step=500, key="ed_empaque")

                    precio_sug_edit, breakdown = calcular_precio_final(
                        total_receta_edit, p_merma, p_ops, costo_mo, p_maq, p_margen, costo_empaque
                    )
                    
                    st.markdown("---")
                    st.markdown(f"""<div style="font-size: 14px;">
                        <b>Subtotal 1</b>: ${breakdown['insumos'] + breakdown['merma']:,.0f}<br>
                        + Ops: ${breakdown['ops']:,.0f} | MO: ${breakdown['mo']:,.0f} | Maq: ${breakdown['maq']:,.0f}<br>
                        <b>Costo Total: ${(precio_sug_edit - breakdown['ganancia'] - breakdown['empaque']):,.0f}</b><br>
                        <span style="color:green">+ Ganancia: ${breakdown['ganancia']:,.0f}</span> | Empaque: ${breakdown['empaque']:,.0f}
                    </div>""", unsafe_allow_html=True)
                    
                    st.markdown(f"#### Precio Sugerido: ${precio_sug_edit:,.0f}")
                    precio_final_edit = st.number_input("Precio Venta Final ($)", value=int(precio_sug_edit), step=500, key="edit_precio_f")
                    
                    if st.button("💾 Guardar Cambios", type="primary", use_container_width=True):
                        try:
                            supabase.table('variaciones').update({
                                "precio": precio_final_edit,
                                "ingredientes_json": json.dumps(st.session_state.edit_ingredientes)
                            }).eq('id', st.session_state.edit_var_id).execute()
                            st.success("¡Actualizado!")
                            st.session_state.edit_var_id = None
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e: st.error(f"Error: {e}")
                    
                    if st.button("Cancelar"):
                        st.session_state.edit_var_id = None
                        st.rerun()

        with tab_base:
            st.subheader("Paso 1: Definir Tipo de Masa")
            c1, c2 = st.columns([2, 1])
            pb_nombre = c1.text_input("Nombre de la Base", placeholder="Ej: Torta Bizcocho")
            pb_cat = c2.selectbox("Categoría", ["Tortas", "Cóctel", "Individuales", "Bollería"])
            pb_img = c1.text_input("URL Imagen", placeholder="http://...")
            
            if st.button("💾 Guardar Base"):
                if pb_nombre:
                    try:
                        exist = supabase.table('productos').select('id').eq('nombre', pb_nombre).execute().data
                        if exist: st.warning("¡Ya existe!")
                        else:
                            supabase.table('productos').insert({"nombre": pb_nombre, "categoria": pb_cat, "imagen_url": pb_img}).execute()
                            st.success(f"Creado: {pb_nombre}")
                            time.sleep(1.5)
                            st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

        with tab_variacion:
            st.subheader("Paso 2: Receta Específica")
            if not lista_productos_base:
                st.warning("Primero crea una Base en la pestaña anterior.")
            else:
                sel_padre = st.selectbox("1. Selecciona el Tipo de Masa", lista_productos_base)
                if sel_padre:
                    id_padre = mapa_productos_base[sel_padre]['id']
                    st.divider()
                    
                    col_sabor, col_tam = st.columns([2, 1])
                    with col_sabor: 
                        var_sabor = st.text_input("2. Sabor / Variedad", placeholder="Ej: Tradicional, Nueces")
                    with col_tam:
                        opciones_tamano = ["1 Kilo", "500 Gramos", "12 Personas", "20 Personas", "30 Personas", "Bandeja 12 Unid", "Individual"]
                        var_tamano = st.selectbox("3. Tamaño", opciones_tamano)

                    nombre_completo = f"{var_sabor} - {var_tamano}" if var_sabor else var_tamano
                    st.info(f"📝 Creando: **{nombre_completo}**")

                    # === 🎛️ CALCULADORA DE LOTE (PAN DE PASCUA) ===
                    st.markdown("##### 🎛️ Configuración de Lote")
                    usar_lote = st.checkbox("¿Es receta por lote? (Ej: Una mezcla rinde para varios panes)", value=False)
                    
                    factor_div = 1.0
                    if usar_lote:
                        factor_div = st.number_input("Rendimiento del Lote (¿Cuántas unidades salen?)", min_value=1.0, value=10.0)
                        st.info(f"💡 Ingresa la receta de la 'Olla Completa'. El sistema dividirá los ingredientes por {factor_div} para sacar el costo unitario.")

                    col_izq, col_der = st.columns([1, 1.2])
                    
                    # --- IZQUIERDA: INGREDIENTES ---
                    with col_izq:
                        st.markdown("##### 🥣 Ingredientes")
                        if 'var_ingredientes' not in st.session_state: 
                            st.session_state.var_ingredientes = []
                        
                        insumo_k = st.selectbox("Insumo", list(mapa_insumos.keys()), index=None, placeholder="Buscar...")
                        if insumo_k:
                            d_ins = mapa_insumos[insumo_k]
                            u_base = d_ins['unidad_medida']
                            st.caption(f"Costo: ${d_ins['costo_unitario']:,.0f} / {u_base}")
                            
                            cc1, cc2 = st.columns(2)
                            label_cant = "Cantidad LOTE" if usar_lote else "Cantidad UNIDAD"
                            v_cant = cc1.number_input(label_cant, min_value=0.0, value=1.0, format="%.2f", step=0.1)
                            
                            opts = [u_base]
                            if u_base == 'kg': opts = ['gr', 'kg', 'cdta', 'cda']
                            elif u_base == 'gr': opts = ['gr', 'kg', 'cdta', 'cda']
                            elif u_base == 'lt': opts = ['ml', 'lt', 'cc', 'cdta', 'cda']
                            elif u_base in ['ml', 'cc']: opts = ['ml', 'lt', 'cc', 'cdta', 'cda']
                            
                            v_uni = cc2.selectbox("Unidad", opts)
                            
                            if st.button("⬇️ Agregar"):
                                if v_cant > 0:
                                    # 1. Normalizar a unidad base del sistema
                                    cant_norm_sistema = convertir_a_base(v_cant, v_uni, u_base)
                                    
                                    # 2. Calcular costo (SIEMPRE con la cantidad normalizada completa)
                                    costo_linea = cant_norm_sistema * d_ins['costo_unitario']
                                    
                                    # 3. GUARDAR la cantidad original ingresada (NO dividir aquí)
                                    st.session_state.var_ingredientes.append({
                                        "nombre": insumo_k, 
                                        "cantidad": v_cant,  # ✅ Guardamos lo que ingresó el usuario
                                        "unidad": v_uni,      # ✅ En la unidad que eligió
                                        "costo": costo_linea, # ✅ Costo total de esa cantidad
                                        "insumo_id": d_ins['id']
                                    })
                                    st.rerun()
                        
                        st.markdown("---")
                        
                        # Calcular costo total según el modo
                        total_receta = 0
                        
                        if usar_lote:
                            st.caption(f"💡 Ficha Técnica del Lote Completo ({int(factor_div)} unidades):")
                        else:
                            st.caption(f"Ficha Técnica ({var_tamano}):")
                        
                        for i, item in enumerate(st.session_state.var_ingredientes):
                            # Recalcular costo actualizado por si cambió el precio del insumo
                            if item['nombre'] in mapa_insumos:
                                d_actual = mapa_insumos[item['nombre']]
                                cant_norm = convertir_a_base(item['cantidad'], item['unidad'], d_actual['unidad_medida'])
                                costo_actual = cant_norm * d_actual['costo_unitario']
                                item['costo'] = costo_actual
                            
                            total_receta += item['costo']
                            
                            # Mostrar ingrediente
                            cant_display = mostrar_cantidad(item['cantidad'])
                            st.markdown(f"**• {cant_display} {item['unidad']} {item['nombre']}** (${item['costo']:,.0f})")
                            
                            if st.button("🗑️", key=f"del_{i}"):
                                st.session_state.var_ingredientes.pop(i)
                                st.rerun()
                        
                        # Mostrar resumen según modo
                        if usar_lote and total_receta > 0:
                            costo_unitario = total_receta / factor_div
                            st.markdown(f"""
                            <div style="background:#e3f2fd; padding:8px; border-radius:5px; margin-top:10px;">
                                <b>Resumen:</b><br>
                                • Costo Lote Completo: ${total_receta:,.0f}<br>
                                • Costo por Unidad: ${costo_unitario:,.0f}
                            </div>
                            """, unsafe_allow_html=True)

                    # --- DERECHA: CALCULADORA COSTOS ---
                    # --- DERECHA: CALCULADORA COSTOS ---
                    # --- DERECHA: CALCULADORA COSTOS ---
                    with col_der:
                        st.markdown("##### 💰 Calculadora de Precios")
                        
                        # Calcular costo total de los ingredientes (del LOTE COMPLETO si aplica)
                        total_ingredientes_lote = sum([x['costo'] for x in st.session_state.var_ingredientes])
                        
                        # Si es modo lote, calcular el costo unitario de ingredientes
                        if usar_lote and total_ingredientes_lote > 0:
                            costo_ingredientes_unitario = total_ingredientes_lote / factor_div
                            st.info(f"Costo Ingredientes por Unidad: **${costo_ingredientes_unitario:,.0f}**")
                            st.caption(f"💡 Costo total de ingredientes del lote: ${total_ingredientes_lote:,.0f}")
                        else:
                            costo_ingredientes_unitario = total_ingredientes_lote
                            st.info(f"Costo Ingredientes: **${costo_ingredientes_unitario:,.0f}**")
                        
                        with st.expander("⚙️ Opciones Avanzadas", expanded=True):
                            c_p1, c_p2 = st.columns(2)
                            p_merma = c_p1.slider("Merma %", 0, 15, 5)
                            p_ops = c_p2.slider("G. Ops %", 0, 30, 15)
                            
                            c_p3, c_p4 = st.columns(2)
                            
                            if usar_lote:
                                costo_mo = c_p3.number_input("Mano Obra $ (TODO el lote)", value=6400, step=500)
                                costo_empaque = c_p4.number_input("Empaque $ (TODO el lote)", value=0, step=500)
                            else:
                                costo_mo = c_p3.number_input("Mano Obra $ (por unidad)", value=6400, step=500)
                                costo_empaque = c_p4.number_input("Empaque $ (por unidad)", value=3000, step=500)
                            
                            p_maq = st.slider("Mantención Maq. %", 0, 20, 5)
                            p_margen = st.slider("Margen Ganancia %", 10, 100, 60)

                        # SOLO calcular si hay ingredientes
                        if total_ingredientes_lote > 0:
                            st.markdown("---")
                            
                            if usar_lote:
                                # MODO LOTE: Calcular sobre el lote completo
                                val_merma = total_ingredientes_lote * (p_merma / 100)
                                sub1 = total_ingredientes_lote + val_merma
                                val_ops = sub1 * (p_ops / 100)
                                sub2 = sub1 + val_ops
                                sub3 = sub2 + costo_mo
                                val_maq = sub3 * (p_maq / 100)
                                sub4 = sub3 + val_maq
                                costo_produccion_lote = sub4
                                val_ganancia = costo_produccion_lote * (p_margen / 100)
                                sub5 = costo_produccion_lote + val_ganancia
                                precio_total_lote = sub5 + costo_empaque
                                precio_unitario_sug = precio_total_lote / factor_div
                                
                                st.markdown(f"""
                                <div style="background:#fff3cd; padding:12px; border-radius:8px; border-left:4px solid #ffc107; font-size:13px;">
                                    <b>📦 Cálculo del Lote ({int(factor_div)} unidades):</b><br><br>
                                    • Ingredientes: ${total_ingredientes_lote:,.0f}<br>
                                    • Merma ({p_merma}%): ${val_merma:,.0f}<br>
                                    • Gastos Ops ({p_ops}%): ${val_ops:,.0f}<br>
                                    • Mano de Obra: ${costo_mo:,.0f}<br>
                                    • Maquinaria ({p_maq}%): ${val_maq:,.0f}<br>
                                    <b>= Costo Producción: ${costo_produccion_lote:,.0f}</b><br><br>
                                    • Ganancia ({p_margen}%): <span style="color:green">${val_ganancia:,.0f}</span><br>
                                    • Empaque: ${costo_empaque:,.0f}<br>
                                    <b style="font-size:15px;">= Precio Total Lote: ${precio_total_lote:,.0f}</b><br><br>
                                    <hr style="margin:8px 0; border:none; border-top:1px solid #ddd;">
                                    <b style="font-size:16px; color:#f2590d;">🔹 Precio Unitario: ${precio_unitario_sug:,.0f}</b><br>
                                    <small style="color:#666;">(${precio_total_lote:,.0f} ÷ {int(factor_div)} unidades)</small>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                # MODO NORMAL
                                precio_unitario_sug, bd = calcular_precio_final(
                                    costo_ingredientes_unitario, p_merma, p_ops, costo_mo, p_maq, p_margen, costo_empaque
                                )
                                st.markdown(f"""
                                <div style="background:#f8f9fa; padding:10px; border-radius:5px; font-size:13px;">
                                    <b>Desglose:</b><br>
                                    Subtotal+Merma: ${bd['insumos']+bd['merma']:,.0f}<br>
                                    + Ops: ${bd['ops']:,.0f} | MO: ${bd['mo']:,.0f} | Maq: ${bd['maq']:,.0f}<br>
                                    <b>Costo Prod: ${(precio_unitario_sug - bd['ganancia'] - bd['empaque']):,.0f}</b><br>
                                    <span style="color:green">+ Ganancia: ${bd['ganancia']:,.0f}</span> | Empaque: ${bd['empaque']:,.0f}
                                </div>
                                """, unsafe_allow_html=True)
                            
                            st.markdown(f"#### Precio Unitario Sugerido: ${precio_unitario_sug:,.0f}")
                            precio_final = st.number_input("Precio Venta Final Unitario ($)", value=int(precio_unitario_sug), step=100)
                            
                            if st.button("💾 Guardar Receta", type="primary", use_container_width=True):
                                if st.session_state.var_ingredientes and var_sabor:
                                    try:
                                        supabase.table('variaciones').insert({
                                            "producto_id": id_padre, "nombre": nombre_completo,
                                            "precio": precio_final, 
                                            "ingredientes_json": json.dumps(st.session_state.var_ingredientes),
                                            "rendimiento": factor_div
                                        }).execute()
                                        st.success(f"✅ Guardado! Precio unitario: ${precio_final:,.0f}")
                                        if usar_lote:
                                            st.info(f"💡 Lote completo: ${precio_final * factor_div:,.0f}")
                                        st.session_state.var_ingredientes = []
                                        time.sleep(1.5)
                                        st.rerun()
                                    except Exception as e: st.error(f"Error: {e}")
                        else:
                            st.markdown("---")
                            st.warning("⚠️ Agrega ingredientes para calcular")
                            
                            # Botón deshabilitado visualmente
                            st.markdown('<p style="color:#999; font-size:14px;">💾 Guardar Receta (Agrega ingredientes primero)</p>', unsafe_allow_html=True)

        with tab_catalogo:
            st.subheader("Catálogo")
            if lista_productos_base:
                try: all_vars = supabase.table('variaciones').select("*").order('nombre').execute().data
                except: all_vars = []
                for p_nombre in lista_productos_base:
                    p_data = mapa_productos_base[p_nombre]
                    variaciones_p = [v for v in all_vars if v['producto_id'] == p_data['id']]
                    with st.expander(f"🎂 {p_nombre} ({len(variaciones_p)} var)"):
                        col_img, col_info, col_actions = st.columns([2, 3, 1])
                        with col_img:
                            if p_data.get('imagen_url'): st.image(p_data['imagen_url'], width=300)
                            else: st.markdown("🖼️")
                        with col_info:
                            st.caption(f"Categoría: **{p_data.get('categoria', 'General')}**")
                            if not variaciones_p: st.info("Sin variedades.")
                            else:
                                for v in variaciones_p:
                                    with st.container():
                                        c_v1, c_v2 = st.columns([3, 1])
                                        c_v1.markdown(f"**{v['nombre']}** - ${v['precio']:,.0f}")
                                        with c_v2:
                                            if st.button("✏️", key=f"edit_{v['id']}"):
                                                st.session_state.edit_var_id = v['id']
                                                st.session_state.edit_var_data = v
                                                try: st.session_state.edit_ingredientes = json.loads(v['ingredientes_json'])
                                                except: st.session_state.edit_ingredientes = []
                                                st.toast("Cargado en Editor ➡️")
                                            if st.button("🗑️", key=f"del_v_{v['id']}"):
                                                supabase.table('variaciones').delete().eq('id', v['id']).execute()
                                                st.rerun()
                                        with st.popover("Ver ingredientes"):
                                            try:
                                                ings = json.loads(v['ingredientes_json'])
                                                for i in ings: st.markdown(f"**• {i['cantidad']} {i['unidad']} {i['nombre']}**")
                                            except: pass
                                    st.divider()
                        with col_actions:
                            with st.popover("⚙️ Config"):
                                new_name_b = st.text_input("Nombre", p_data['nombre'], key=f"n_{p_data['id']}")
                                new_cat_b = st.selectbox("Cat", ["Tortas", "Cóctel", "Individuales", "Bollería"], key=f"c_{p_data['id']}")
                                new_img_b = st.text_input("URL", p_data.get('imagen_url', ''), key=f"i_{p_data['id']}")
                                if st.button("Guardar", key=f"save_b_{p_data['id']}"):
                                    supabase.table('productos').update({"nombre": new_name_b, "categoria": new_cat_b, "imagen_url": new_img_b}).eq('id', p_data['id']).execute()
                                    st.rerun()
                            if st.button("🗑️ Borrar", key=f"del_b_{p_data['id']}"):
                                supabase.table('productos').delete().eq('id', p_data['id']).execute()
                                st.rerun()
            else: st.info("Crea una masa base primero.")

    # ==========================================
    # 📦 INVENTARIO (V10: DECIMALES LIMPIOS)
    # ==========================================
    elif menu == "📦 Inventario":
        st.title("📦 Inventario y Costos")

        # --- HELPER CONVERSIÓN ---
        def normalizar_cantidad(cantidad, unidad_origen, unidad_destino):
            if unidad_origen == unidad_destino: return cantidad
            if unidad_destino == 'kg' and unidad_origen == 'gr': return cantidad / 1000
            if unidad_destino == 'gr' and unidad_origen == 'kg': return cantidad * 1000
            if unidad_destino == 'lt' and (unidad_origen == 'ml' or unidad_origen == 'cc'): return cantidad / 1000
            if (unidad_destino == 'ml' or unidad_destino == 'cc') and unidad_origen == 'lt': return cantidad * 1000
            return None
        
        def mostrar_cantidad(valor, unidad=None):
            if unidad == 'unidades': return str(int(valor))
            if valor == int(valor): return str(int(valor))
            return f"{valor:.2f}".rstrip('0').rstrip('.')

        # Carga de datos
        insumos_existentes = []
        mapa_insumos = {}
        if supabase:
            try:
                data = supabase.table('insumos').select("*").order('nombre').execute().data
                insumos_existentes = [i['nombre'] for i in data]
                mapa_insumos = {i['nombre']: i for i in data}
            except Exception as e:
                st.error(f"Error cargando inventario: {e}")

        # TABS
        tab_compra, tab_nuevo, tab_precios, tab_stock = st.tabs([
            "🛒 Registrar Compra", 
            "✨ Crear Nuevo Insumo", 
            "💲 Actualizar Precios Mercado", 
            "📋 Ver y Ajustar Stock"
        ])

        # ---------------------------------------------------------
        # TAB 1: REGISTRAR COMPRA
        # ---------------------------------------------------------
        with tab_compra:
            st.subheader("Ingreso de Stock Real (Compras)")
            if not insumos_existentes:
                st.warning("Crea insumos primero.")
            else:
                c_sel, c_info = st.columns([2, 2])
                with c_sel:
                    insumo_selec = st.selectbox("Producto Comprado", insumos_existentes, index=None, placeholder="Buscar...")
                
                if insumo_selec:
                    datos = mapa_insumos[insumo_selec]
                    u_base = datos['unidad_medida']
                    with c_info:
                        st.info(f"Precio Ref: **${datos['costo_unitario']:,.0f} / {u_base}**")

                    c1, c2, c3 = st.columns(3)
                    
                    opts = [u_base]
                    if u_base == 'kg': opts = ['kg', 'gr']
                    elif u_base == 'gr': opts = ['gr', 'kg']
                    elif u_base == 'lt': opts = ['lt', 'ml', 'cc']
                    elif u_base == 'ml': opts = ['ml', 'lt']
                    elif u_base == 'unidades': opts = ['unidades']
                    
                    with c2:
                        u_compra = st.selectbox("Unidad Compra", opts, key="c_u")
                    with c1:
                        if u_compra == 'unidades':
                            cant_input = st.number_input("Cantidad", min_value=0, value=1, step=1, key="c_c")
                        else:
                            cant_input = st.number_input("Cantidad", min_value=0.0, value=1.0, format="%.2f", step=0.1, key="c_c")
                    with c3:
                        total_pago = st.number_input("Total Pagado ($)", min_value=0, value=0, step=1000, key="c_p")

                    if st.button("✅ Ingresar Stock"):
                        cant_norm = normalizar_cantidad(cant_input, u_compra, u_base) if u_compra != u_base else cant_input
                        if cant_norm:
                            nuevo_precio_ref = total_pago / cant_norm if cant_norm > 0 else datos['costo_unitario']
                            supabase.table('insumos').update({
                                "stock_actual": datos['stock_actual'] + cant_norm,
                                "costo_unitario": nuevo_precio_ref
                            }).eq('id', datos['id']).execute()
                            
                            registrar_gasto(total_pago, f"Compra: {insumo_selec}")
                            st.toast("✅ Stock ingresado.")
                            time.sleep(1)
                            st.rerun()

        # ---------------------------------------------------------
        # TAB 2: CREAR NUEVO INSUMO
        # ---------------------------------------------------------
        with tab_nuevo:
            st.subheader("Definir Nuevo Insumo")
            c_nom, c_uni = st.columns([2, 1])
            new_nombre = c_nom.text_input("Nombre Genérico", placeholder="Ej: Leche Condensada")
            new_unidad = c_uni.selectbox("Unidad Base del Sistema", ["kg", "gr", "lt", "ml", "unidades"], help="¿Cómo quieres medir esto en tus recetas?")

            st.markdown("##### 🏷️ Precio de Referencia Inicial")
            c_form1, c_form2, c_form3 = st.columns(3)
            
            opts = [new_unidad]
            if new_unidad == 'kg': opts = ['kg', 'gr']
            elif new_unidad == 'gr': opts = ['gr', 'kg']
            elif new_unidad == 'lt': opts = ['lt', 'ml', 'cc']
            elif new_unidad == 'ml': opts = ['ml', 'lt']
            elif new_unidad == 'unidades': opts = ['unidades']
            
            with c_form2: uni_ref = st.selectbox("Unidad del envase", opts, key="n_u")
            with c_form1: 
                if uni_ref == 'unidades':
                    cant_ref = st.number_input("Contenido", min_value=0, value=1, step=1, key="n_c")
                else:
                    cant_ref = st.number_input("Contenido", min_value=0.0, value=1.0, format="%.2f", step=0.1, key="n_c")
            with c_form3: precio_ref = st.number_input("Precio ($)", min_value=0, value=0, step=1000, key="n_p")
            
            if st.button("💾 Crear Ficha"):
                if new_nombre:
                    cant_norm = normalizar_cantidad(cant_ref, uni_ref, new_unidad) if uni_ref != new_unidad else cant_ref
                    if cant_norm and cant_norm > 0:
                        costo_base_calc = precio_ref / cant_norm
                        try:
                            supabase.table('insumos').insert({
                                "nombre": new_nombre, 
                                "unidad_medida": new_unidad, 
                                "stock_actual": 0, 
                                "costo_unitario": costo_base_calc
                            }).execute()
                            st.success(f"✅ Creado: {new_nombre}")
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e: st.error(f"Error: {e}")

        # ---------------------------------------------------------
        # TAB 3: ACTUALIZAR PRECIOS
        # ---------------------------------------------------------
        with tab_precios:
            st.subheader("💲 Actualizador de Precios")
            if insumos_existentes:
                col_sel, col_calc = st.columns([1, 2])
                with col_sel:
                    insumo_upd = st.selectbox("Selecciona Producto", insumos_existentes, index=None)
                    if insumo_upd:
                        d = mapa_insumos[insumo_upd]
                        st.info(f"Unidad: **{d['unidad_medida']}**\nCosto: **${d['costo_unitario']:,.2f}**")
                
                with col_calc:
                    if insumo_upd:
                        st.markdown(f"##### 🧮 Datos del Envase ({insumo_upd})")
                        c_p1, c_p2, c_p3 = st.columns([1.5, 1, 1.5])
                        
                        u_base = mapa_insumos[insumo_upd]['unidad_medida']
                        opts_p = [u_base]
                        if u_base == 'kg': opts_p = ['kg', 'gr']
                        elif u_base == 'gr': opts_p = ['gr', 'kg']
                        elif u_base == 'lt': opts_p = ['lt', 'ml', 'cc']
                        elif u_base == 'ml': opts_p = ['ml', 'lt']
                        elif u_base == 'unidades': opts_p = ['unidades']
                        
                        with c_p2: uni_envase = st.selectbox("Unidad", opts_p, key="p_u")
                        with c_p1: 
                            if uni_envase == 'unidades':
                                cant_envase = st.number_input("Contenido", min_value=0, value=1, step=1, key="p_c")
                            else:
                                cant_envase = st.number_input("Contenido", min_value=0.0, value=1.0, format="%.2f", step=0.1, key="p_c")
                        with c_p3: precio_envase = st.number_input("Precio Total ($)", min_value=0, value=0, step=1000, key="p_p")
                        
                        cant_norm_p = normalizar_cantidad(cant_envase, uni_envase, u_base) if uni_envase != u_base else cant_envase
                        if cant_norm_p and cant_norm_p > 0 and precio_envase > 0:
                            nuevo_costo_base = precio_envase / cant_norm_p
                            if u_base == 'gr' and cant_envase < 1 and uni_envase == 'gr':
                                st.warning("⚠️ Cuidado: Pusiste menos de 1 gramo.")
                            st.success(f"💡 El **{u_base}** vale **${nuevo_costo_base:,.2f}**")
                            if st.button("💾 Actualizar Precio Base", type="primary"):
                                supabase.table('insumos').update({"costo_unitario": nuevo_costo_base}).eq('id', mapa_insumos[insumo_upd]['id']).execute()
                                st.rerun()

                st.divider()
                df_view = pd.DataFrame(list(mapa_insumos.values()))
                if not df_view.empty:
                    st.dataframe(df_view[['nombre', 'unidad_medida', 'costo_unitario']], use_container_width=True)

        # ---------------------------------------------------------
        # TAB 4: VER Y AJUSTAR STOCK
        # ---------------------------------------------------------
        with tab_stock:
            st.subheader("Control de Bodega")
            
            with st.expander("➕ Agregar / Ajustar Stock Manualmente", expanded=True):
                st.caption("Usa esto para agregar sobras (ej: 'me quedan 200gr') o corregir el inventario sin registrar gasto.")
                
                c_aj_1, c_aj_2 = st.columns([2, 2])
                
                with c_aj_1:
                    item_ajuste = st.selectbox("Producto", insumos_existentes, index=None, key="aj_item")
                
                if item_ajuste:
                    dat_aj = mapa_insumos[item_ajuste]
                    u_base = dat_aj['unidad_medida']
                    
                    with c_aj_2:
                        tipo_ajuste = st.radio("Acción", ["➕ Sumar al stock", "📌 Fijar stock total"], horizontal=True, label_visibility="collapsed")
                    
                    opts_aj = [u_base]
                    if u_base == 'kg': opts_aj = ['kg', 'gr']
                    elif u_base == 'gr': opts_aj = ['gr', 'kg']
                    elif u_base == 'lt': opts_aj = ['lt', 'ml', 'cc']
                    elif u_base == 'ml': opts_aj = ['ml', 'lt']
                    elif u_base == 'unidades': opts_aj = ['unidades']
                    
                    c_aj_3, c_aj_4 = st.columns([1.5, 1.5])
                    
                    with c_aj_4:
                        uni_ajuste = st.selectbox("Unidad", opts_aj, key="aj_uni")
                    
                    with c_aj_3:
                        if uni_ajuste == 'unidades':
                            cant_ajuste = st.number_input("Cantidad", min_value=0, value=1, step=1, key="aj_cant")
                        else:
                            cant_ajuste = st.number_input("Cantidad", min_value=0.0, value=1.0, format="%.2f", step=0.1, key="aj_cant")
                    
                    cant_norm_aj = normalizar_cantidad(cant_ajuste, uni_ajuste, u_base) if uni_ajuste != u_base else cant_ajuste
                    
                    if cant_norm_aj is not None:
                        nuevo_stock = 0
                        msg_accion = ""
                        
                        if tipo_ajuste == "➕ Sumar al stock":
                            nuevo_stock = dat_aj['stock_actual'] + cant_norm_aj
                            msg_accion = f"Sumados {mostrar_cantidad(cant_ajuste, uni_ajuste)} {uni_ajuste}"
                        else:
                            nuevo_stock = cant_norm_aj
                            msg_accion = f"Stock fijado en {mostrar_cantidad(cant_ajuste, uni_ajuste)} {uni_ajuste}"
                        
                        stock_display = mostrar_cantidad(nuevo_stock, u_base)
                        
                        if st.button(f"💾 Guardar: Stock quedará en {stock_display} {u_base}", use_container_width=True):
                            supabase.table('insumos').update({"stock_actual": nuevo_stock}).eq('id', dat_aj['id']).execute()
                            st.success(f"✅ {msg_accion}. Nuevo total: {stock_display} {u_base}")
                            time.sleep(1.5)
                            st.rerun()

            st.divider()
            
            if insumos_existentes:
                df = pd.DataFrame(list(mapa_insumos.values()))
                st.dataframe(df[['nombre', 'stock_actual', 'unidad_medida', 'costo_unitario']], use_container_width=True)
                
                with st.popover("🗑️ Borrar Insumo"):
                    to_del = st.selectbox("Eliminar permanentemente:", insumos_existentes, index=None)
                    if to_del:
                        if st.button(f"Confirmar Borrado de {to_del}"):
                            supabase.table('insumos').delete().eq('nombre', to_del).execute()
                            st.rerun()
                            
    # ==========================================
    # ⚙️ CONFIGURACIÓN (V3: CORRECCIÓN DE TABLA 'GASTOS')
    # ==========================================
    elif menu == "⚙️ Configuración":
        st.title("⚙️ Configuración del Sistema")
        st.info(f"Usuario: {st.session_state.usuario_actual} | Rol: {st.session_state.rol_actual}")
        
        st.divider()
        st.subheader("👥 Usuarios")
        if supabase:
            try:
                usuarios = supabase.table('usuarios').select("*").execute().data
                if usuarios: st.dataframe(pd.DataFrame(usuarios)[['nombre', 'username', 'rol']], hide_index=True, use_container_width=True)
            except: pass

        st.divider()
        
        # --- ZONA DE PELIGRO ---
        st.subheader("🚨 Zona de Mantenimiento")
        
        c1, c2 = st.columns(2)
        with c1:
            with st.expander("🗑️ Borrar Inventario Físico"):
                st.warning("Borra todos los insumos y stock.")
                if st.checkbox("Confirmar borrado inventario", key="chk_inv_del"):
                    if st.button("💣 EJECUTAR BORRADO INV"):
                        supabase.table('insumos').delete().neq('id', 0).execute()
                        st.success("Inventario Reiniciado")
                        time.sleep(2)
                        st.rerun()

        with c2:
            with st.expander("💰 Borrar Historial Financiero"):
                st.warning("Borra el historial de ventas y gastos. Dashboard a $0.")
                if st.checkbox("Confirmar borrado financiero", key="chk_fin_del"):
                    if st.button("💣 EJECUTAR BORRADO FINANZAS"):
                        try:
                            # CORRECCIÓN AQUÍ: 'gastos' en lugar de 'transacciones'
                            supabase.table('gastos').delete().neq('id', 0).execute()
                            st.success("Historial Financiero Reiniciado")
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

# --- ARRANQUE ---
if not st.session_state.authenticated:
    login_screen()
else:
    main_app()