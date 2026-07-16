import streamlit as st
import pandas as pd
from datetime import date
from io import BytesIO
import plotly.express as px

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

st.set_page_config(
    page_title="Ausentismo Operativo",
    page_icon="📋",
    layout="centered"
)

# CSS mobile-friendly:
# Tablas con scroll horizontal y botones adaptados a dispositivos móviles.
st.markdown(
    """
    <style>
        .stDataFrame {
            overflow-x: auto;
        }

        @media (max-width: 640px) {
            .stMetric {
                font-size: 0.85rem;
            }

            div[data-testid="stHorizontalBlock"] > div {
                min-width: 0 !important;
            }
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------------------------
# CONEXIÓN SUPABASE
# ---------------------------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

TABLE = "registros_ausentismo"

# ---------------------------------------------------------------------------
# CATÁLOGOS
# ---------------------------------------------------------------------------
AREAS = [
    "Reparto",
    "Almacén"
]

RUTAS = [
    f"Ruta {i}"
    for i in range(1, 23)
]

TURNOS = [
    "Turno Matutino",
    "Turno Vespertino",
    "Turno Nocturno"
]

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
# FUNCIONES DE DATOS
# ---------------------------------------------------------------------------
def insertar_registro(
    fecha,
    area,
    empleado,
    ruta_turno,
    causa,
    comentario,
    supervisor
):
    """
    Inserta un nuevo registro en Supabase.
    """

    supabase.table(TABLE).insert(
        {
            "fecha": str(fecha),
            "area": area,
            "empleado": empleado,
            "ruta": ruta_turno,
            "causa": causa,
            "comentario": comentario,
            "supervisor": supervisor,
        }
    ).execute()


@st.cache_data(ttl=15)
def cargar_datos():
    """
    Descarga todos los registros de Supabase y los convierte
    en un DataFrame de pandas.
    """

    res = (
        supabase
        .table(TABLE)
        .select("*")
        .order("fecha", desc=True)
        .order("id", desc=True)
        .execute()
    )

    df = pd.DataFrame(res.data)

    # Compatibilidad con registros anteriores que no tengan área.
    if not df.empty and "area" not in df.columns:
        df["area"] = "Reparto"

    return df


def eliminar_registro(reg_id):
    """
    Elimina un registro de Supabase mediante su ID.
    """

    (
        supabase
        .table(TABLE)
        .delete()
        .eq("id", reg_id)
        .execute()
    )


def convertir_excel(df):
    """
    Convierte un DataFrame en un archivo Excel almacenado en memoria.

    El archivo incluye:
    - Encabezados resaltados.
    - Filtros automáticos.
    - Primera fila congelada.
    - Ancho automático de columnas.
    - Formato de fecha.
    """

    output = BytesIO()

    # Copia para no modificar el DataFrame original.
    df_exportar = df.copy()

    # Orden recomendado para las columnas.
    columnas_ordenadas = [
        "id",
        "fecha",
        "area",
        "empleado",
        "ruta",
        "causa",
        "comentario",
        "supervisor"
    ]

    # Solo se utilizan las columnas que realmente existan.
    columnas_disponibles = [
        columna
        for columna in columnas_ordenadas
        if columna in df_exportar.columns
    ]

    # Agrega al final cualquier columna adicional que pueda existir.
    columnas_adicionales = [
        columna
        for columna in df_exportar.columns
        if columna not in columnas_disponibles
    ]

    df_exportar = df_exportar[
        columnas_disponibles + columnas_adicionales
    ]

    # Convertir fecha a un formato reconocido por Excel.
    if "fecha" in df_exportar.columns:
        df_exportar["fecha"] = pd.to_datetime(
            df_exportar["fecha"],
            errors="coerce"
        )

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
        datetime_format="DD/MM/YYYY"
    ) as writer:

        df_exportar.to_excel(
            writer,
            index=False,
            sheet_name="Registros"
        )

        worksheet = writer.sheets["Registros"]

        # Congelar la primera fila.
        worksheet.freeze_panes = "A2"

        # Agregar filtros automáticos.
        worksheet.auto_filter.ref = worksheet.dimensions

        # Dar formato a los encabezados.
        for celda in worksheet[1]:
            celda.font = celda.font.copy(bold=True)
            celda.alignment = celda.alignment.copy(
                horizontal="center",
                vertical="center"
            )

        # Aplicar formato de fecha.
        if "fecha" in df_exportar.columns:
            numero_columna_fecha = (
                df_exportar.columns.get_loc("fecha") + 1
            )

            for fila in range(2, worksheet.max_row + 1):
                worksheet.cell(
                    row=fila,
                    column=numero_columna_fecha
                ).number_format = "DD/MM/YYYY"

        # Ajustar automáticamente el ancho de las columnas.
        for columna in worksheet.columns:
            largo_maximo = 0
            letra_columna = columna[0].column_letter

            for celda in columna:
                try:
                    valor = celda.value

                    if valor is not None:
                        largo_valor = len(str(valor))
                        largo_maximo = max(
                            largo_maximo,
                            largo_valor
                        )

                except Exception:
                    pass

            # Máximo de 45 para evitar columnas demasiado anchas.
            ancho_columna = min(
                largo_maximo + 2,
                45
            )

            worksheet.column_dimensions[
                letra_columna
            ].width = ancho_columna

    output.seek(0)

    return output.getvalue()


# ---------------------------------------------------------------------------
# INTERFAZ PRINCIPAL
# ---------------------------------------------------------------------------
st.title("📋 Ausentismo Operativo")

modo = st.radio(
    "Vista",
    [
        "✍️ Captura",
        "📊 Dashboard",
        "🗂️ Datos"
    ],
    horizontal=True,
    label_visibility="collapsed"
)

# ---------------------------------------------------------------------------
# CAPTURA
# ---------------------------------------------------------------------------
if modo == "✍️ Captura":

    st.subheader("Captura rápida")

    # El área se mantiene fuera del formulario para que Streamlit
    # pueda actualizar dinámicamente el selector de Ruta o Turno.
    area = st.selectbox(
        "Área",
        AREAS,
        key="area_selector"
    )

    with st.form(
        "form_captura",
        clear_on_submit=True
    ):

        fecha = st.date_input(
            "Fecha",
            value=date.today()
        )

        supervisor = st.text_input(
            "Supervisor",
            placeholder="Tu nombre"
        )

        empleado = st.text_input(
            "Empleado",
            placeholder="Nombre del empleado"
        )

        if st.session_state.get(
            "area_selector",
            "Reparto"
        ) == "Reparto":

            ruta_turno = st.selectbox(
                "Ruta",
                RUTAS
            )

        else:

            ruta_turno = st.selectbox(
                "Turno",
                TURNOS
            )

        causa = st.selectbox(
            "Causa",
            CAUSAS
        )

        comentario = st.text_input(
            "Comentario (opcional)",
            placeholder="Breve nota"
        )

        enviado = st.form_submit_button(
            "➕ Guardar registro",
            use_container_width=True,
            type="primary"
        )

        if enviado:

            if not empleado.strip() or not supervisor.strip():

                st.error(
                    "⚠️ Falta el nombre del empleado o del supervisor."
                )

            else:

                area_val = st.session_state.get(
                    "area_selector",
                    "Reparto"
                )

                try:
                    insertar_registro(
                        fecha=fecha,
                        area=area_val,
                        empleado=empleado.strip(),
                        ruta_turno=ruta_turno,
                        causa=causa,
                        comentario=comentario.strip(),
                        supervisor=supervisor.strip()
                    )

                    st.cache_data.clear()

                    st.success(
                        f"✅ {empleado.strip()} "
                        f"({area_val}) — {causa}"
                    )

                except Exception as error:
                    st.error(
                        f"❌ No fue posible guardar el registro: {error}"
                    )

    st.divider()
    st.caption("Últimos registros")

    try:
        df_rec = cargar_datos()

        if not df_rec.empty:

            columnas_recientes = [
                columna
                for columna in [
                    "fecha",
                    "area",
                    "empleado",
                    "ruta",
                    "causa"
                ]
                if columna in df_rec.columns
            ]

            st.dataframe(
                df_rec[columnas_recientes].head(8),
                use_container_width=True,
                hide_index=True
            )

        else:
            st.info("Aún no hay registros.")

    except Exception as error:
        st.error(
            f"❌ No fue posible consultar los registros: {error}"
        )


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
elif modo == "📊 Dashboard":

    try:
        df = cargar_datos()

    except Exception as error:
        st.error(
            f"❌ No fue posible cargar el dashboard: {error}"
        )
        st.stop()

    if df.empty:

        st.info(
            "Captura registros para ver el dashboard."
        )

    else:

        df["fecha"] = pd.to_datetime(
            df["fecha"],
            errors="coerce"
        )

        # Eliminar únicamente registros cuya fecha no pueda interpretarse.
        df = df.dropna(
            subset=["fecha"]
        )

        if df.empty:
            st.warning(
                "No existen registros con fechas válidas."
            )
            st.stop()

        with st.expander("🔎 Filtros"):

            rango = st.date_input(
                "Rango de fechas",
                value=(
                    df["fecha"].min().date(),
                    df["fecha"].max().date()
                )
            )

            area_sel = st.multiselect(
                "Área",
                AREAS,
                default=[]
            )

            causas_sel = st.multiselect(
                "Causa",
                CAUSAS,
                default=[]
            )

        df_f = df.copy()

        if isinstance(rango, tuple) and len(rango) == 2:

            fecha_inicio = pd.to_datetime(
                rango[0]
            )

            fecha_fin = pd.to_datetime(
                rango[1]
            )

            df_f = df_f[
                (df_f["fecha"] >= fecha_inicio)
                & (df_f["fecha"] <= fecha_fin)
            ]

        if area_sel and "area" in df_f.columns:
            df_f = df_f[
                df_f["area"].isin(area_sel)
            ]

        if causas_sel and "causa" in df_f.columns:
            df_f = df_f[
                df_f["causa"].isin(causas_sel)
            ]

        # KPIs.
        k1, k2 = st.columns(2)

        k1.metric(
            "Total eventos",
            len(df_f)
        )

        empleados_distintos = (
            df_f["empleado"].nunique()
            if "empleado" in df_f.columns
            else 0
        )

        k2.metric(
            "Empleados distintos",
            empleados_distintos
        )

        k3, k4 = st.columns(2)

        if not df_f.empty and "causa" in df_f.columns:
            causa_top = df_f["causa"].mode()

            causa_top = (
                causa_top.iloc[0]
                if not causa_top.empty
                else "—"
            )
        else:
            causa_top = "—"

        if not df_f.empty and "ruta" in df_f.columns:
            conteo_rutas = df_f["ruta"].value_counts()

            ruta_top = (
                conteo_rutas.idxmax()
                if not conteo_rutas.empty
                else "—"
            )
        else:
            ruta_top = "—"

        k3.metric(
            "Causa raíz #1",
            causa_top
        )

        k4.metric(
            "Más afectado",
            ruta_top
        )

        st.divider()

        t1, t2, t3, t4, t5 = st.tabs(
            [
                "📊 Causas",
                "🥧 Por área",
                "🚚 Reparto",
                "🏭 Almacén",
                "📈 Tendencia"
            ]
        )

        # Gráfica de causas.
        with t1:

            st.markdown(
                "**Causa raíz (Pareto)**"
            )

            if not df_f.empty and "causa" in df_f.columns:

                conteo = (
                    df_f["causa"]
                    .value_counts()
                    .reset_index()
                )

                conteo.columns = [
                    "causa",
                    "eventos"
                ]

                fig1 = px.bar(
                    conteo,
                    x="causa",
                    y="eventos",
                    text="eventos",
                    color_discrete_sequence=[
                        "#2E86AB"
                    ]
                )

                fig1.update_layout(
                    xaxis_title="",
                    yaxis_title="",
                    xaxis_tickangle=-35
                )

                st.plotly_chart(
                    fig1,
                    use_container_width=True
                )

            else:
                st.info(
                    "Sin datos para el filtro actual."
                )

        # Gráfica por área.
        with t2:

            st.markdown(
                "**Distribución por área**"
            )

            if not df_f.empty and "area" in df_f.columns:

                area_count = (
                    df_f["area"]
                    .value_counts()
                    .reset_index()
                )

                area_count.columns = [
                    "area",
                    "eventos"
                ]

                fig0 = px.pie(
                    area_count,
                    names="area",
                    values="eventos",
                    color_discrete_map={
                        "Reparto": "#2E86AB",
                        "Almacén": "#F18F01"
                    }
                )

                st.plotly_chart(
                    fig0,
                    use_container_width=True
                )

            else:
                st.info(
                    "Sin datos para el filtro actual."
                )

        # Gráfica reparto.
        with t3:

            st.markdown(
                "**Reparto — por ruta**"
            )

            if "area" in df_f.columns:

                df_rep = df_f[
                    df_f["area"] == "Reparto"
                ]

            else:
                df_rep = pd.DataFrame()

            if not df_rep.empty and "ruta" in df_rep.columns:

                rutas_conteo = (
                    df_rep["ruta"]
                    .value_counts()
                    .reset_index()
                )

                rutas_conteo.columns = [
                    "ruta",
                    "eventos"
                ]

                fig2 = px.bar(
                    rutas_conteo,
                    x="ruta",
                    y="eventos",
                    text="eventos",
                    color_discrete_sequence=[
                        "#2E86AB"
                    ]
                )

                fig2.update_layout(
                    xaxis_title="",
                    yaxis_title=""
                )

                st.plotly_chart(
                    fig2,
                    use_container_width=True
                )

            else:
                st.info(
                    "Sin datos de Reparto en el filtro actual."
                )

        # Gráfica almacén.
        with t4:

            st.markdown(
                "**Almacén — por turno**"
            )

            if "area" in df_f.columns:

                df_alm = df_f[
                    df_f["area"] == "Almacén"
                ]

            else:
                df_alm = pd.DataFrame()

            if not df_alm.empty and "ruta" in df_alm.columns:

                turnos_conteo = (
                    df_alm["ruta"]
                    .value_counts()
                    .reset_index()
                )

                turnos_conteo.columns = [
                    "turno",
                    "eventos"
                ]

                fig3 = px.bar(
                    turnos_conteo,
                    x="turno",
                    y="eventos",
                    text="eventos",
                    color_discrete_sequence=[
                        "#F18F01"
                    ]
                )

                fig3.update_layout(
                    xaxis_title="",
                    yaxis_title=""
                )

                st.plotly_chart(
                    fig3,
                    use_container_width=True
                )

            else:
                st.info(
                    "Sin datos de Almacén en el filtro actual."
                )

        # Tendencia.
        with t5:

            st.markdown(
                "**Tendencia diaria por área**"
            )

            if (
                not df_f.empty
                and "area" in df_f.columns
                and "fecha" in df_f.columns
            ):

                tend = (
                    df_f
                    .groupby(
                        [
                            df_f["fecha"].dt.date,
                            "area"
                        ]
                    )
                    .size()
                    .reset_index(
                        name="eventos"
                    )
                )

                tend.columns = [
                    "fecha",
                    "area",
                    "eventos"
                ]

                fig4 = px.line(
                    tend,
                    x="fecha",
                    y="eventos",
                    color="area",
                    markers=True,
                    color_discrete_map={
                        "Reparto": "#2E86AB",
                        "Almacén": "#F18F01"
                    }
                )

                st.plotly_chart(
                    fig4,
                    use_container_width=True
                )

            else:
                st.info(
                    "Sin datos para el filtro actual."
                )

        st.divider()

        st.markdown(
            "**Top empleados con más eventos**"
        )

        if not df_f.empty and "empleado" in df_f.columns:

            top_emp = (
                df_f["empleado"]
                .value_counts()
                .head(10)
                .reset_index()
            )

            top_emp.columns = [
                "empleado",
                "eventos"
            ]

            st.dataframe(
                top_emp,
                use_container_width=True,
                hide_index=True
            )

        else:
            st.info(
                "Sin empleados para el filtro actual."
            )

        # Conservamos la descarga CSV existente.
        csv = df_f.to_csv(
            index=False
        ).encode(
            "utf-8-sig"
        )

        st.download_button(
            label="⬇️ Descargar CSV",
            data=csv,
            file_name="reporte_ausentismo.csv",
            mime="text/csv",
            use_container_width=True
        )


# ---------------------------------------------------------------------------
# TODOS LOS DATOS
# ---------------------------------------------------------------------------
else:

    st.subheader(
        "Todos los registros"
    )

    try:
        df_all = cargar_datos()

    except Exception as error:
        st.error(
            f"❌ No fue posible consultar los registros: {error}"
        )
        st.stop()

    if df_all.empty:

        st.info(
            "Aún no hay registros disponibles."
        )

    else:

        # Mostrar todos los registros.
        st.dataframe(
            df_all,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            f"Total de registros disponibles: {len(df_all):,}"
        )

        # Crear Excel con todos los registros de Supabase.
        try:
            archivo_excel = convertir_excel(
                df_all
            )

            st.download_button(
                label="📥 Descargar todos los registros en Excel",
                data=archivo_excel,
                file_name=(
                    "registros_ausentismo_"
                    f"{date.today():%Y-%m-%d}.xlsx"
                ),
                mime=(
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                use_container_width=True,
                type="primary"
            )

        except Exception as error:
            st.error(
                f"❌ No fue posible generar el archivo Excel: {error}"
            )

        st.divider()

        # Se conserva la opción para eliminar registros.
        if "id" in df_all.columns:

            id_borrar = st.selectbox(
                "Eliminar registro por ID",
                df_all["id"].tolist()
            )

            if st.button(
                "🗑️ Eliminar",
                use_container_width=True
            ):

                try:
                    eliminar_registro(
                        id_borrar
                    )

                    st.cache_data.clear()

                    st.success(
                        f"Registro {id_borrar} eliminado."
                    )

                    st.rerun()

                except Exception as error:
                    st.error(
                        f"❌ No fue posible eliminar el registro: {error}"
                    )

        else:
            st.warning(
                "No se encontró la columna ID. "
                "No es posible habilitar la eliminación."
            )
