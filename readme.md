# 🧁 TV Repostería - Sistema ERP

Sistema de gestión empresarial completo para TV Repostería, desarrollado con Streamlit y Supabase.

## 🚀 Características

- **📊 Dashboard Financiero**: Control de ingresos, gastos y balance en tiempo real
- **📌 Gestión de Pedidos**: Sistema Kanban con 4 estados (Pendiente → En Proceso → Listo → Entregado)
- **🧁 Catálogo de Productos**: Con imágenes, categorías y fichas técnicas
- **📦 Inventario Inteligente**: 
  - Descuento automático de stock al entregar pedidos
  - Devolución automática al cancelar entregas
  - Registro de gastos vinculado a compras
- **🔐 Sistema de Login**: Acceso multiusuario con roles
- **📈 Reportes Visuales**: Gráficos de evolución mensual

## 🛠️ Tecnologías

- **Frontend/Backend**: Streamlit
- **Base de Datos**: Supabase (PostgreSQL)
- **Visualización**: Altair Charts
- **Gestión de Datos**: Pandas

## 📦 Instalación Local

1. Clona el repositorio:
```bash
git clone https://github.com/TU_USUARIO/tv-reposteria-erp.git
cd tv-reposteria-erp
```

2. Instala las dependencias:
```bash
pip install -r requirements.txt
```

3. Configura las credenciales de Supabase:
   - Crea una carpeta `.streamlit/` en la raíz del proyecto
   - Crea el archivo `.streamlit/secrets.toml` con:
```toml
[supabase]
url = "TU_URL_DE_SUPABASE"
key = "TU_ANON_KEY"
```

4. Ejecuta la aplicación:
```bash
streamlit run erp.py
```

## 🌐 Despliegue en Streamlit Cloud

1. Sube el proyecto a GitHub
2. Ve a [share.streamlit.io](https://share.streamlit.io)
3. Conecta tu repositorio
4. Configura los secrets en el panel de Streamlit Cloud
5. ¡Deploy! 🚀

## 🔑 Credenciales por Defecto

**Usuario**: `fresia`  
**Contraseña**: `peque1183`

⚠️ **Importante**: Cambia las credenciales después del primer login.

## 📊 Estructura de la Base de Datos

### Tablas principales:
- `usuarios`: Gestión de accesos
- `pedidos`: Órdenes de clientes
- `recetas`: Productos del catálogo
- `insumos`: Inventario de materias primas
- `gastos`: Registro contable

## 🎨 Capturas de Pantalla

### Dashboard Financiero
Control total de las finanzas del negocio con gráficos en tiempo real.

### Gestión de Pedidos (Kanban)
Sistema visual para seguimiento de producción.

### Catálogo de Productos
Con imágenes, precios y fichas técnicas completas.

## 👥 Autor

**TV Repostería**  
- Instagram: [@tvreposteria](https://www.instagram.com/tvreposteria/)
- WhatsApp: +56 9 8884 4973

## 📄 Licencia

Este proyecto es privado y está diseñado específicamente para TV Repostería.

---

Hecho con ❤️ y 🍰 por TV Repostería