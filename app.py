import streamlit as st
import pandas as pd
from datetime import date
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

# ─── FIX SSL RED CORPORATIVA DANONE ────────────────────────────────────────
import httpx
_orig_client_init = httpx.Client.__init__
def _client_no_ssl(self, *args, **kwargs):
    kwargs["verify"] = False
    _orig_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _client_no_ssl

_orig_async_init = httpx.AsyncClient.__init__
def _async_no_ssl(self, *args, **kwargs):
    kwargs["verify"] = False
    _orig_async_init(self, *args, **kwargs)
httpx.AsyncClient.__init__ = _async_no_ssl
# ───────────────────────────────────────────────────────────────────────────

from supabase import create_client

st.set_page_config(page_title="Ausentismo Operativo", page_icon="📋", layout="centered")
st_autorefresh(interval=10 * 60 * 1000, silent=True)

# CSS mobile-friendly: tablas scroll horizontal, botones full width en celu
st.markdown("""
<style>
    .stDataFrame { overflow-x: auto; }
    @media (max-width: 640px) {
        .stMetric { font-size: 0.85rem; }
        div[data-testid="stHorizontalBlock"] > div { min-width: 0 !important; }
    }
</style>
""", unsafe_allow_html=True)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
TABLE = "registros_ausentismo"

# ---------------------------------------------------------------------------
# CATÁLOGOS
# ---------------------------------------------------------------------------
AREAS = ["Reparto", "Almacén"]
RUTAS = [f"Ruta {i}" for i in range(1, 23)]
TURNOS = ["Turno Matutino", "Turno Vespertino", "Turno Nocturno"]
CAUSAS = [
    "Falta injustificada",
    "Incapacidad",
    "Permiso con goce",
    "Permiso sin goce",
    "Retardo / Llegó tarde",
    "Vacaciones",
    "Accidente de trabajo",
    "Problema personal / familiar",
    "Problema de transporte",
    "Renuncia / Baja",
    "Otro",
]

# ---------------------------------------------------------------------------
# DATOS
# ---------------------------------------------------------------------------
def insertar_registro(fecha, area, empleado, ruta_turno, causa, comentario, supervisor):
    supabase.table(TABLE).insert({
        "fecha": str(fecha),
        "area": area,
        "empleado": empleado,
        "ruta": ruta_turno,
        "causa": causa,
        "comentario": comentario,
        "supervisor": supervisor,
    }).execute()

@st.cache_data(ttl=15)
def cargar_datos():
    res = supabase.table(TABLE).select("*").order("fecha", desc=True).order("id", desc=True).execute()
    df = pd.DataFrame(res.data)
    if not df.empty and "area" not in df.columns:
        df["area"] = "Reparto"
    return df

def eliminar_registro(reg_id):
    supabase.table(TABLE).delete().eq("id", reg_id).execute()

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.title("📋 Ausentismo Operativo")

modo = st.radio("Vista", ["✍️ Captura", "📊 Dashboard", "🗂️ Datos"],
                horizontal=True, label_visibility="collapsed")

# --- CAPTURA ----------------------------------------------------------------
if modo == "✍️ Captura":
    st.subheader("Captura rápida")

    # Área FUERA del form para que re-renderice dinámicamente
    area = st.selectbox("Área", AREAS, key="area_selector")

    with st.form("form_captura", clear_on_submit=True):
        fecha = st.date_input("Fecha", value=date.today())
        supervisor = st.text_input("Supervisor", placeholder="Tu nombre")
        empleado = st.text_input("Empleado", placeholder="Nombre del empleado")

        if st.session_state.get("area_selector", "Reparto") == "Reparto":
            ruta_turno = st.selectbox("Ruta", RUTAS)
        else:
            ruta_turno = st.selectbox("Turno", TURNOS)

        causa = st.selectbox("Causa", CAUSAS)
        comentario = st.text_input("Comentario (opcional)", placeholder="Breve nota")

        enviado = st.form_submit_button("➕ Guardar registro", use_container_width=True, type="primary")

        if enviado:
            if not empleado or not supervisor:
                st.error("⚠️ Falta el nombre del empleado o del supervisor.")
            else:
                area_val = st.session_state.get("area_selector", "Reparto")
                insertar_registro(fecha, area_val, empleado.strip(), ruta_turno,
                                  causa, comentario.strip(), supervisor.strip())
                st.cache_data.clear()
                st.success(f"✅ {empleado} ({area_val}) — {causa}")

    st.divider()
    st.caption("Últimos registros")
    df_rec = cargar_datos()
    if not df_rec.empty:
        cols = [c for c in ["fecha", "area", "empleado", "ruta", "causa"] if c in df_rec.columns]
        st.dataframe(df_rec[cols].head(8), use_container_width=True, hide_index=True)
    else:
        st.info("Aún no hay registros.")

# --- DASHBOARD --------------------------------------------------------------
elif modo == "📊 Dashboard":
    df = cargar_datos()
    if df.empty:
        st.info("Captura registros para ver el dashboard.")
    else:
        df["fecha"] = pd.to_datetime(df["fecha"])

        with st.expander("🔎 Filtros"):
            rango = st.date_input("Rango de fechas",
                value=(df["fecha"].min().date(), df["fecha"].max().date()))
            area_sel = st.multiselect("Área", AREAS, default=[])
            causas_sel = st.multiselect("Causa", CAUSAS, default=[])

        df_f = df.copy()
        if isinstance(rango, tuple) and len(rango) == 2:
            df_f = df_f[(df_f["fecha"] >= pd.to_datetime(rango[0])) &
                        (df_f["fecha"] <= pd.to_datetime(rango[1]))]
        if area_sel:
            df_f = df_f[df_f["area"].isin(area_sel)]
        if causas_sel:
            df_f = df_f[df_f["causa"].isin(causas_sel)]

        # KPIs — 2 columnas max para que no apriete en celu
        k1, k2 = st.columns(2)
        k1.metric("Total eventos", len(df_f))
        k2.metric("Empleados distintos", df_f["empleado"].nunique())
        k3, k4 = st.columns(2)
        causa_top = df_f["causa"].mode()[0] if not df_f.empty else "—"
        ruta_top = df_f["ruta"].value_counts().idxmax() if not df_f.empty else "—"
        k3.metric("Causa raíz #1", causa_top)
        k4.metric("Más afectado", ruta_top)

        st.divider()

        # Gráficas en tabs → cada una ocupa 100% del ancho, perfecto en celu
        t1, t2, t3, t4, t5 = st.tabs(["📊 Causas", "🥧 Por área", "🚚 Reparto", "🏭 Almacén", "📈 Tendencia"])

        with t1:
            st.markdown("**Causa raíz (Pareto)**")
            conteo = df_f["causa"].value_counts().reset_index()
            conteo.columns = ["causa", "eventos"]
            fig1 = px.bar(conteo, x="causa", y="eventos", text="eventos",
                          color_discrete_sequence=["#2E86AB"])
            fig1.update_layout(xaxis_title="", yaxis_title="", xaxis_tickangle=-35)
            st.plotly_chart(fig1, use_container_width=True)

        with t2:
            st.markdown("**Distribución por área**")
            area_count = df_f["area"].value_counts().reset_index()
            area_count.columns = ["area", "eventos"]
            fig0 = px.pie(area_count, names="area", values="eventos",
                          color_discrete_map={"Reparto": "#2E86AB", "Almacén": "#F18F01"})
            st.plotly_chart(fig0, use_container_width=True)

        with t3:
            st.markdown("**Reparto — por ruta**")
            df_rep = df_f[df_f["area"] == "Reparto"]
            if not df_rep.empty:
                r = df_rep["ruta"].value_counts().reset_index()
                r.columns = ["ruta", "eventos"]
                fig2 = px.bar(r, x="ruta", y="eventos", text="eventos",
                              color_discrete_sequence=["#2E86AB"])
                fig2.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Sin datos de Reparto en el filtro actual.")

        with t4:
            st.markdown("**Almacén — por turno**")
            df_alm = df_f[df_f["area"] == "Almacén"]
            if not df_alm.empty:
                t_count = df_alm["ruta"].value_counts().reset_index()
                t_count.columns = ["turno", "eventos"]
                fig3 = px.bar(t_count, x="turno", y="eventos", text="eventos",
                              color_discrete_sequence=["#F18F01"])
                fig3.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.info("Sin datos de Almacén en el filtro actual.")

        with t5:
            st.markdown("**Tendencia diaria por área**")
            tend = df_f.groupby([df_f["fecha"].dt.date, "area"]).size().reset_index(name="eventos")
            tend.columns = ["fecha", "area", "eventos"]
            fig4 = px.line(tend, x="fecha", y="eventos", color="area", markers=True,
                           color_discrete_map={"Reparto": "#2E86AB", "Almacén": "#F18F01"})
            st.plotly_chart(fig4, use_container_width=True)

        st.divider()
        st.markdown("**Top empleados con más eventos**")
        top_emp = df_f["empleado"].value_counts().head(10).reset_index()
        top_emp.columns = ["empleado", "eventos"]
        st.dataframe(top_emp, use_container_width=True, hide_index=True)

        csv = df_f.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Descargar CSV", csv, "reporte_ausentismo.csv", "text/csv",
                           use_container_width=True)

# --- DATOS ------------------------------------------------------------------
else:
    st.subheader("Todos los registros")
    df_all = cargar_datos()
    st.dataframe(df_all, use_container_width=True, hide_index=True)

    if not df_all.empty:
        st.divider()
        id_borrar = st.selectbox("Eliminar registro por ID", df_all["id"].tolist())
        if st.button("🗑️ Eliminar", use_container_width=True):
            eliminar_registro(id_borrar)
            st.cache_data.clear()
            st.success(f"Registro {id_borrar} eliminado.")
            st.rerun()
