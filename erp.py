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
    except:
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
    # 📌 PEDIDOS
    # ==========================================
    elif menu == "📌 Pedidos":
        col_header, col_btn = st.columns([3, 1])
        with col_header:
            st.title("Gestión de Pedidos")
            st.markdown("Control de producción y devoluciones.")
        
        prod_dict = {}
        if supabase:
            try:
                prs = supabase.table('recetas').select("*").execute().data
                for p in prs: prod_dict[p['nombre']] = p
            except: pass

        with col_btn:
            st.write("")
            with st.popover("➕ Crear Nuevo Pedido", use_container_width=True):
                st.markdown("### 🛒 Nuevo Pedido")
                c1, c2 = st.columns(2)
                n_cli = c1.text_input("Nombre Cliente")
                n_tel = c2.text_input("Teléfono")
                n_fec = st.date_input("Fecha Entrega")
                st.divider()
                
                if 'carrito_pedido' not in st.session_state: 
                    st.session_state.carrito_pedido = []
                
                if not prod_dict:
                    st.warning("Crea productos primero.")
                else:
                    col_prod, col_cant, col_add = st.columns([2, 1, 1])
                    prod_selec = col_prod.selectbox("Producto", list(prod_dict.keys()), key="sel_prod")
                    cant_prod = col_cant.number_input("Cantidad", 1, 100, 1, key="cant_prod")
                    
                    if col_add.button("Añadir"):
                        p_unit = prod_dict[prod_selec]['precio_venta']
                        st.session_state.carrito_pedido.append({
                            "producto": prod_selec,
                            "cantidad": cant_prod,
                            "precio_unit": p_unit,
                            "subtotal": cant_prod * p_unit
                        })
                    
                    if st.session_state.carrito_pedido:
                        df_c = pd.DataFrame(st.session_state.carrito_pedido)
                        st.dataframe(df_c[['producto', 'cantidad', 'subtotal']], hide_index=True)
                        total = df_c['subtotal'].sum()
                        st.markdown(f"**Total: ${total:,.0f}**")
                        n_not = st.text_area("Notas / Dedicatoria")
                        
                        if st.button("Confirmar Pedido", type="primary"):
                            if n_cli:
                                supabase.table('pedidos').insert({
                                    "cliente_nombre": n_cli,
                                    "cliente_telefono": n_tel,
                                    "fecha_entrega": str(n_fec),
                                    "estado": "Pendiente",
                                    "detalle_json": json.dumps(st.session_state.carrito_pedido),
                                    "total_pedido": total,
                                    "notas_extra": n_not
                                }).execute()
                                st.session_state.carrito_pedido = []
                                st.rerun()

        # KANBAN
        if supabase:
            try:
                ped = supabase.table('pedidos').select("*").neq('estado', 'Cancelado').order('fecha_entrega').execute().data
            except:
                ped = []
            
            c1, c2, c3, c4 = st.columns(4)
            cols = {"Pendiente": c1, "En Proceso": c2, "Listo": c3, "Entregado": c4}
            with c1: st.markdown("##### 📝 Pendientes")
            with c2: st.markdown("##### 🔥 En Horno")
            with c3: st.markdown("##### ✅ Para Retiro")
            with c4: st.markdown("##### 🚚 Entregados")
            
            if not ped:
                st.info("No hay pedidos activos.")
            
            for p in ped:
                est = p.get('estado', 'Pendiente')
                col = cols.get(est, c1)
                
                det_html = ""
                if p.get('detalle_json'):
                    try:
                        its = json.loads(p['detalle_json'])
                        det_html = "<ul style='font-size:0.8em;padding-left:15px;color:#555;margin:5px 0;'>"
                        for i in its:
                            det_html += f"<li>{i['cantidad']}x {i['producto']}</li>"
                        det_html += "</ul>"
                    except: pass
                
                b_cls = "badge-gray"
                if est == "Pendiente": b_cls = "badge-yellow"
                elif est == "En Proceso": b_cls = "badge-blue"
                elif est == "Listo": b_cls = "badge-green"
                
                with col:
                    st.markdown(f"""
                    <div class="kanban-card">
                        <div style="display:flex;justify-content:space-between;">
                            <span style="font-weight:bold;color:#f2590d">#{p['id']}</span>
                            <span class="badge {b_cls}">{est}</span>
                        </div>
                        <div style="font-weight:bold;">{p['cliente_nombre']}</div>
                        {det_html}
                        <div style="font-weight:bold;text-align:right;">${p.get('total_pedido', 0):,.0f}</div>
                        <div style="color:#666;font-size:0.8em;margin-top:5px;">📅 {p['fecha_entrega']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    c_act, c_cancel = st.columns([3, 1])
                    with c_act:
                        if est == 'Pendiente':
                            if st.button("Cocinar ➡️", key=f"c{p['id']}"): 
                                cambiar_estado_pedido(p['id'], "En Proceso")
                        elif est == 'En Proceso':
                            if st.button("Listo ✅", key=f"l{p['id']}"): 
                                cambiar_estado_pedido(p['id'], "Listo")
                        elif est == 'Listo':
                            if st.button("Entregar 🎁", key=f"e{p['id']}"): 
                                cambiar_estado_pedido(p['id'], "Entregado", p)
                    
                    with c_cancel:
                        if st.button("❌", key=f"del_{p['id']}", help="Cancelar y devolver stock"):
                            cambiar_estado_pedido(p['id'], "Cancelado", p)

    # ==========================================
    # 🧁 PRODUCTOS
    # ==========================================
    elif menu == "🧁 Mis Productos":
        st.title("Catálogo de Productos y Fichas Técnicas")
        st.markdown("Aquí creas lo que vendes. Asigna categoría e ingredientes para calcular costos.")

        ins_d = {}
        if supabase:
            ir = supabase.table('insumos').select("*").execute().data
            for i in ir: 
                ins_d[i['nombre']] = i
        
        tab_catalogo, tab_nuevo = st.tabs(["📖 Ver Catálogo", "➕ Crear Nuevo Producto"])
        
        # --- CREAR PRODUCTO ---
        with tab_nuevo:
            st.subheader("Nuevo Producto")
            
            if 'nuevo_prod_ingredientes' not in st.session_state:
                st.session_state.nuevo_prod_ingredientes = []
            
            col_datos, col_ing = st.columns([1, 1])
            
            with col_datos:
                n_nombre = st.text_input("Nombre del Producto", placeholder="Ej: Torta Amor 20p")
                n_cat = st.selectbox("Categoría", ["Tortas", "Cóctel Dulce", "Cóctel Salado", "Pasteles (Individuales)", "Otros"])
                n_img = st.text_input("URL Imagen (Opcional)", placeholder="https://imgur.com/...", help="Pega aquí un link directo a la foto de tu producto.")
                
                st.divider()
                st.markdown("##### Ficha Técnica (Ingredientes)")
                
                if ins_d:
                    opciones_insumos = list(ins_d.keys())
                    insumo_selec = st.selectbox("Selecciona Insumo", opciones_insumos)
                    unidad_insumo = ins_d[insumo_selec]['unidad_medida']
                    
                    c_cant, c_btn = st.columns([2, 1])
                    cantidad = c_cant.number_input(f"Cantidad ({unidad_insumo})", min_value=0.0, step=0.1, format="%.2f")
                    
                    if c_btn.button("⬇️ Agregar"):
                        if cantidad > 0:
                            st.session_state.nuevo_prod_ingredientes.append({
                                "nombre": insumo_selec,
                                "cantidad": cantidad,
                                "unidad": unidad_insumo,
                                "id_insumo": ins_d[insumo_selec]['id']
                            })
                            st.toast(f"Agregado: {insumo_selec}")
            
            with col_ing:
                st.markdown("##### 📋 Resumen del Producto")
                st.info(f"Categoría: **{n_cat}**")
                
                # Previsualizar imagen
                if n_img:
                    st.image(n_img, caption="Vista previa", use_container_width=True)
                
                if st.session_state.nuevo_prod_ingredientes:
                    df_prev = pd.DataFrame(st.session_state.nuevo_prod_ingredientes)
                    st.dataframe(df_prev[['nombre', 'cantidad', 'unidad']], hide_index=True, use_container_width=True)
                    
                    # Calcular Costo
                    costo_total = 0
                    for item in st.session_state.nuevo_prod_ingredientes:
                        if item['nombre'] in ins_d:
                            precio = ins_d[item['nombre']]['costo_unitario']
                            costo_total += (item['cantidad'] * precio)
                    
                    st.metric("Costo Producción", f"${costo_total:,.0f}")
                    
                    margen = st.slider("Margen Ganancia (%)", 10, 100, 40)
                    if margen < 100:
                        precio_sug = costo_total / (1 - (margen/100))
                    else:
                        precio_sug = 0
                    
                    precio_final = st.number_input("Precio de Venta Final ($)", value=int(precio_sug), step=100)
                    
                    if st.button("💾 Guardar Producto", type="primary", use_container_width=True):
                        if n_nombre:
                            datos = {
                                "nombre": n_nombre,
                                "categoria": n_cat,
                                "ingredientes_json": json.dumps(st.session_state.nuevo_prod_ingredientes),
                                "precio_venta": precio_final,
                                "imagen_url": n_img
                            }
                            supabase.table('recetas').insert(datos).execute()
                            st.success(f"Producto '{n_nombre}' creado!")
                            st.session_state.nuevo_prod_ingredientes = []
                            time.sleep(1)
                            st.rerun()
        
        # --- CATÁLOGO ---
        with tab_catalogo:
            st.subheader("Mis Productos")
            
            prods_db = []
            if supabase:
                try:
                    prods_db = supabase.table('recetas').select("*").execute().data
                except: pass
            
            if prods_db:
                df_prods = pd.DataFrame(prods_db)
                
                # Filtro por Categoría
                cats = df_prods['categoria'].unique() if 'categoria' in df_prods.columns else []
                if len(cats) > 0:
                    cat_filter = st.multiselect("Filtrar por Categoría", cats)
                    if cat_filter:
                        df_prods = df_prods[df_prods['categoria'].isin(cat_filter)]
                
                # Grid de Productos
                for index, row in df_prods.iterrows():
                    cat_show = row.get('categoria', 'Sin Categoría')
                    precio_show = row.get('precio_venta', 0)
                    
                    with st.expander(f"🧁 {row['nombre']} ({cat_show}) - ${precio_show:,.0f}"):
                        col_img, col_info = st.columns([1, 2])
                        
                        with col_img:
                            if row.get('imagen_url'):
                                st.image(row['imagen_url'], use_container_width=True)
                            else:
                                st.info("Sin imagen")
                        
                        with col_info:
                            st.markdown(f"**Categoría:** {cat_show}")
                            st.markdown(f"**Precio:** ${precio_show:,.0f}")
                            st.markdown("**Ingredientes:**")
                            try:
                                ings = json.loads(row['ingredientes_json'])
                                for i in ings:
                                    st.text(f"• {i['cantidad']} {i['unidad']} {i['nombre']}")
                            except:
                                st.text("Sin detalle.")
                            
                            if st.button("🗑️ Borrar Producto", key=f"del_{row['id']}"):
                                supabase.table('recetas').delete().eq('id', row['id']).execute()
                                st.rerun()

    # ==========================================
    # 📦 INVENTARIO
    # ==========================================
    elif menu == "📦 Inventario":
        with st.expander("➕ Ingresar Compra de Insumos (Registrar Gasto)", expanded=False):
            c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
            with c1: n_nom = st.text_input("Nombre Insumo")
            with c2: n_uni = st.selectbox("Unidad", ["kg", "unidades", "lt", "gr", "ml", "caja", "paquete"])
            with c3: n_cos = st.number_input("Costo Unitario", min_value=0)
            with c4: n_stk = st.number_input("Cantidad Comprada", min_value=0.0)
            
            registrar_en_finanzas = st.checkbox("Registrar como Gasto en Finanzas", value=True)
            
            with c5:
                st.write("")
                st.write("")
                if st.button("Ingresar Stock"):
                    if n_nom:
                        # 1. Actualizar Stock
                        existente = supabase.table('insumos').select("*").eq('nombre', n_nom).execute().data
                        if existente:
                            id_exist = existente[0]['id']
                            stock_ant = existente[0]['stock_actual']
                            nuevo_stock = stock_ant + n_stk
                            supabase.table('insumos').update({
                                "stock_actual": nuevo_stock,
                                "costo_unitario": n_cos
                            }).eq('id', id_exist).execute()
                        else:
                            supabase.table('insumos').insert({
                                "nombre": n_nom,
                                "unidad_medida": n_uni,
                                "costo_unitario": n_cos,
                                "stock_actual": n_stk
                            }).execute()
                        
                        # 2. Registrar Gasto Financiero
                        if registrar_en_finanzas:
                            total_compra = n_cos * n_stk
                            registrar_gasto(total_compra, f"Compra: {n_nom} ({n_stk}{n_uni})")
                            st.toast(f"Gasto de ${total_compra} registrado", icon="💸")
                        
                        st.success("Inventario Actualizado")
                        time.sleep(1)
                        st.rerun()
        
        st.title("📦 Inventario Actual")
        
        if supabase:
            response = supabase.table('insumos').select("*").order('nombre').execute()
            datos_reales = response.data
            if datos_reales:
                df = pd.DataFrame(datos_reales)
                
                st.markdown("### 📋 Control de Bodega")
                df_edit = st.data_editor(
                    df,
                    key="inv_edit",
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={
                        "id": None,
                        "stock_actual": st.column_config.NumberColumn("Stock", format="%.2f"),
                        "costo_unitario": st.column_config.NumberColumn("Costo $", format="$%d")
                    }
                )
                
                if st.button("💾 Guardar Ajustes Manuales"):
                    recs = df_edit.to_dict('records')
                    for r in recs:
                        d = {k: v for k, v in r.items() if k in ['id', 'nombre', 'unidad_medida', 'stock_actual', 'costo_unitario']}
                        if pd.isna(d.get('id')):
                            del d['id']
                        supabase.table('insumos').upsert(d).execute()
                    
                    # Borrar eliminados
                    ids_orig = set(df['id'].tolist())
                    ids_new = set(df_edit['id'].dropna().tolist())
                    for i_del in (ids_orig - ids_new):
                        supabase.table('insumos').delete().eq('id', i_del).execute()
                    
                    st.success("Guardado")
                    st.rerun()

    # ==========================================
    # ⚙️ CONFIGURACIÓN
    # ==========================================
    elif menu == "⚙️ Configuración":
        st.title("Configuración del Sistema")
        st.text_input("Nombre de la Empresa", value="TV Repostería")
        st.write("Versión del Sistema: 6.1 Full Stack con Login")
        
        st.divider()
        st.subheader("Gestión de Usuarios")
        
        if supabase:
            usuarios = supabase.table('usuarios').select("*").execute().data
            if usuarios:
                df_usuarios = pd.DataFrame(usuarios)
                st.dataframe(df_usuarios[['nombre', 'username', 'rol']], hide_index=True)

# --- ARRANQUE ---
if not st.session_state.authenticated:
    login_screen()
else:
    main_app()