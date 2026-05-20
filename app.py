import streamlit as st
import pandas as pd
import requests

st.set_page_config(
    page_title="Agente Vinted — Evaluador de Lotes",
    page_icon="👕",
    layout="wide"
)

PRECIOS_BASE = {
    "Timberland":      {"med": 44.9, "p75": 60.0, "min": 10.0, "max": 150.0},
    "Umbro":           {"med": 40.0, "p75": 55.0, "min": 8.0,  "max": 120.0},
    "Lacoste":         {"med": 39.9, "p75": 55.0, "min": 13.0, "max": 120.0},
    "Ralph Lauren":    {"med": 32.5, "p75": 45.0, "min": 8.0,  "max": 95.0},
    "Kappa":           {"med": 28.2, "p75": 40.0, "min": 2.5,  "max": 80.0},
    "The North Face":  {"med": 25.5, "p75": 38.0, "min": 10.0, "max": 90.0},
    "Levis":           {"med": 25.2, "p75": 35.0, "min": 9.9,  "max": 75.0},
    "Dickies":         {"med": 24.0, "p75": 35.0, "min": 4.99, "max": 80.0},
    "Tommy Hilfiger":  {"med": 20.0, "p75": 30.0, "min": 8.0,  "max": 80.0},
    "Carhartt":        {"med": 19.9, "p75": 30.0, "min": 3.5,  "max": 90.0},
    "Nike":            {"med": 18.9, "p75": 28.0, "min": 2.5,  "max": 80.0},
    "Reebok":          {"med": 18.4, "p75": 28.0, "min": 8.0,  "max": 70.0},
    "Adidas":          {"med": 15.8, "p75": 22.0, "min": 2.5,  "max": 60.0},
    "Champion":        {"med": 14.0, "p75": 20.0, "min": 9.95, "max": 50.0},
    "Fila":            {"med": 12.5, "p75": 18.0, "min": 3.0,  "max": 45.0},
    "Nautica":         {"med": 8.0,  "p75": 12.0, "min": 4.5,  "max": 30.0},
    "Pepe Jeans":      {"med": 25.0, "p75": 34.0, "min": 8.0,  "max": 70.0},
    "Calvin Klein":    {"med": 11.9, "p75": 20.0, "min": 4.0,  "max": 55.0},
    "Guess":           {"med": 14.0, "p75": 25.0, "min": 1.0,  "max": 60.0},
    "Armani Exchange": {"med": 20.0, "p75": 45.0, "min": 2.0,  "max": 110.0},
}

# Tasa de venta media general para lotes mixtos por kg
TASA_VENTA_GENERAL = 0.68
PIEZAS_POR_KG = 4.0  # media para ropa de abrigo/sudaderas

def cargar_precios_csv(archivo):
    try:
        df = pd.read_csv(archivo)
        if "precio_num" in df.columns:
            df["precio_final"] = pd.to_numeric(df["precio_num"], errors="coerce")
        elif "precio_raw" in df.columns:
            df["precio_final"] = (
                df["precio_raw"].astype(str)
                .str.replace("€", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
            )
        else:
            st.error("El CSV no tiene columna precio_num ni precio_raw")
            return None, None

        df = df.dropna(subset=["precio_final"])
        df = df[df["precio_final"].between(1, 300)]

        resumen = (
            df.groupby("marca_busqueda")["precio_final"]
            .agg(med="median", p75=lambda x: x.quantile(0.75),
                 min="min", max="max")
            .reset_index()
            .rename(columns={"marca_busqueda": "marca"})
        )
        precios = {}
        for _, row in resumen.iterrows():
            precios[row["marca"]] = {
                "med": round(row["med"], 2),
                "p75": round(row["p75"], 2),
                "min": round(row["min"], 2),
                "max": round(row["max"], 2),
            }
        return precios, df
    except Exception as e:
        st.error(f"Error al leer CSV: {e}")
        return None, None

def calcular_lote(marcas_sel, kg_total, precio_kg, precios):
    coste = kg_total * precio_kg
    piezas_totales = round(kg_total * PIEZAS_POR_KG)

    # Precio medio ponderado de las marcas seleccionadas
    precios_marcas = [precios[m]["med"] for m in marcas_sel if m in precios]
    if not precios_marcas:
        return None
    precio_med_pond = sum(precios_marcas) / len(precios_marcas)

    piezas_vendidas = round(piezas_totales * TASA_VENTA_GENERAL)
    ingresos = round(piezas_vendidas * precio_med_pond, 2)
    beneficio = round(ingresos - coste, 2)
    roi = round((beneficio / coste) * 100, 1) if coste > 0 else 0
    margen = round((beneficio / ingresos) * 100, 1) if ingresos > 0 else 0
    precio_max_kg = round((ingresos * 0.5) / kg_total, 2) if kg_total > 0 else 0

    # Ranking marcas del lote de mejor a peor
    ranking = sorted(
        [(m, precios[m]["med"]) for m in marcas_sel if m in precios],
        key=lambda x: -x[1]
    )

    return {
        "coste": coste,
        "ingresos": ingresos,
        "beneficio": beneficio,
        "roi": roi,
        "margen": margen,
        "precio_max_kg": precio_max_kg,
        "piezas_totales": piezas_totales,
        "piezas_vendidas": piezas_vendidas,
        "precio_med_pond": round(precio_med_pond, 2),
        "ranking": ranking,
    }

def llamar_agente(api_key, resultado, marcas_sel, kg_total, precio_kg, precios):
    contexto_precios = "\n".join([
        f"- {m}: precio mediano {precios[m]['med']}€" for m in marcas_sel if m in precios
    ])
    prompt = f"""Eres un experto en compraventa de ropa de segunda mano en Vinted España, especializado en lotes por kilos.

LOTE A EVALUAR:
- Peso: {kg_total} kg a {precio_kg} €/kg → Coste total: {resultado['coste']:.2f}€
- Marcas declaradas por el proveedor: {', '.join(marcas_sel)}
- Piezas estimadas: {resultado['piezas_totales']} (~{PIEZAS_POR_KG} piezas/kg)
- Precio medio ponderado de venta en Vinted: {resultado['precio_med_pond']}€/pieza
- Tasa de venta estimada: {int(TASA_VENTA_GENERAL*100)}%
- Ingresos esperados: {resultado['ingresos']}€
- Beneficio neto: {resultado['beneficio']}€
- ROI: {resultado['roi']}%
- Precio máximo seguro por kg: {resultado['precio_max_kg']}€

PRECIOS REALES DE VINTED (scraping reciente):
{contexto_precios}

Dame un análisis experto en español (máximo 200 palabras) con:
1. Veredicto claro: comprar / no comprar / negociar
2. Qué marcas del lote son las más valiosas
3. Riesgo principal de este lote
4. Consejo concreto de acción"""

    with st.spinner("El agente IA está analizando el lote..."):
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
    resp_json = response.json()
    if "content" in resp_json:
        return resp_json["content"][0]["text"]
    else:
        error_msg = resp_json.get("error", {}).get("message", str(resp_json))
        return f"⚠️ Error de la API: {error_msg}"


# ── UI ───────────────────────────────────────────────────────

st.title("👕 Agente Vinted — Evaluador de Lotes")
st.caption("Describe el lote como te lo vende el proveedor — sin adivinar cantidades ni estado")

with st.sidebar:
    st.header("Configuración")
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    if api_key:
        st.success("API Key cargada ✓")
    else:
        st.warning("API Key no encontrada")

    st.divider()
    st.subheader("Actualizar precios")
    st.caption("Sube el CSV del script R de scraping")
    csv_file = st.file_uploader("vinted_lote_*.csv", type="csv")

    precios_activos = PRECIOS_BASE.copy()
    df_csv = None
    if csv_file:
        nuevos, df_csv = cargar_precios_csv(csv_file)
        if nuevos:
            precios_activos.update(nuevos)
            st.success(f"✓ {len(nuevos)} marcas actualizadas")

    st.divider()
    st.caption("Marcas en el agente:")
    for m, d in sorted(precios_activos.items(), key=lambda x: -x[1]["med"]):
        st.caption(f"**{m}**: {d['med']}€")

# ── PARÁMETROS ───────────────────────────────────────────────
st.subheader("¿Cuánto pesa el lote y a qué precio?")
col1, col2 = st.columns(2)
with col1:
    kg_total = st.number_input("Peso total (kg)", min_value=1, max_value=500, value=20)
with col2:
    precio_kg = st.number_input("Precio pagado (€/kg)", min_value=0.5,
                                 max_value=50.0, value=13.5, step=0.5)

# ── MARCAS DEL LOTE ──────────────────────────────────────────
st.subheader("¿Qué marcas dice el proveedor que hay en el lote?")
st.caption("Selecciona todas las que mencione — no hace falta saber cantidades ni estado")

marcas_disponibles = sorted(precios_activos.keys())

marcas_sel = st.multiselect(
    "Marcas declaradas por el proveedor",
    options=marcas_disponibles,
    default=["Nike", "Ralph Lauren", "Lacoste", "Tommy Hilfiger", "Adidas"],
    label_visibility="collapsed"
)

if marcas_sel:
    # Mostrar precio mediano de cada marca seleccionada
    cols = st.columns(min(len(marcas_sel), 5))
    for i, m in enumerate(marcas_sel):
        if m in precios_activos:
            with cols[i % 5]:
                st.metric(m, f"{precios_activos[m]['med']}€", help="Precio mediano en Vinted España")

st.divider()

# ── EVALUAR ──────────────────────────────────────────────────
if st.button("🔍 Evaluar lote", type="primary", use_container_width=True):
    if not marcas_sel:
        st.warning("Selecciona al menos una marca")
    else:
        resultado = calcular_lote(marcas_sel, kg_total, precio_kg, precios_activos)

        if resultado:
            st.subheader("Resultado")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Inversión", f"{resultado['coste']:.2f} €")
            k2.metric("Ingresos est.", f"{resultado['ingresos']:.2f} €",
                      delta=f"+{resultado['beneficio']:.2f} €")
            k3.metric("ROI", f"{resultado['roi']}%")
            k4.metric("Precio máx. seguro", f"{resultado['precio_max_kg']} €/kg")

            roi = resultado["roi"]
            if roi >= 200:
                st.success(f"✅ COMPRA MUY RECOMENDADA — ROI del {roi}%")
            elif roi >= 100:
                st.success(f"✅ COMPRA RECOMENDADA — ROI del {roi}%")
            elif roi >= 50:
                st.warning(f"⚠️ RENTABLE CON MARGEN AJUSTADO — ROI del {roi}%")
            elif roi >= 0:
                st.warning(f"⚠️ BARELY RENTABLE — Negocia el precio. ROI del {roi}%")
            else:
                st.error(f"❌ NO RECOMENDADO — Genera pérdidas. ROI del {roi}%")

            # Info estimaciones
            st.info(
                f"📦 Estimación basada en {resultado['piezas_totales']} piezas "
                f"({PIEZAS_POR_KG} piezas/kg) · {int(TASA_VENTA_GENERAL*100)}% tasa de venta "
                f"· precio medio ponderado {resultado['precio_med_pond']}€/pieza"
            )

            # Ranking marcas
            st.subheader("Ranking de marcas del lote")
            df_rank = pd.DataFrame(resultado["ranking"], columns=["Marca", "Precio mediano Vinted"])
            df_rank["Precio mediano Vinted"] = df_rank["Precio mediano Vinted"].apply(lambda x: f"{x:.2f} €")
            df_rank.index += 1
            st.dataframe(df_rank, use_container_width=True)

            # Agente IA
            st.subheader("🤖 Análisis del Agente IA")
            if not api_key:
                st.info("Añade tu API Key en Secrets para activar el análisis IA.")
            else:
                analisis = llamar_agente(
                    api_key, resultado, marcas_sel,
                    kg_total, precio_kg, precios_activos
                )
                st.markdown(analisis)

if df_csv is not None:
    with st.expander("Ver datos del CSV cargado"):
        st.dataframe(df_csv.head(50), use_container_width=True)
