import streamlit as st
import pandas as pd
import requests
import json

st.set_page_config(
    page_title="Agente Vinted — Evaluador de Lotes",
    page_icon="👕",
    layout="wide"
)

PRECIOS_BASE = {
    "Lacoste":         {"med": 29.9, "p75": 55.0, "min": 13.0, "max": 120.0},
    "Ralph Lauren":    {"med": 24.0, "p75": 40.0, "min": 8.0,  "max": 95.0},
    "Pepe Jeans":      {"med": 25.0, "p75": 34.0, "min": 8.0,  "max": 70.0},
    "Tommy Hilfiger":  {"med": 23.4, "p75": 38.0, "min": 10.0, "max": 80.0},
    "Levis":           {"med": 23.0, "p75": 35.0, "min": 9.9,  "max": 75.0},
    "Armani Exchange": {"med": 20.0, "p75": 45.0, "min": 2.0,  "max": 110.0},
    "Guess":           {"med": 14.0, "p75": 25.0, "min": 1.0,  "max": 60.0},
    "Nike":            {"med": 13.6, "p75": 22.0, "min": 2.0,  "max": 80.0},
    "Calvin Klein":    {"med": 11.9, "p75": 20.0, "min": 4.0,  "max": 55.0},
    "Adidas":          {"med": 10.0, "p75": 16.0, "min": 4.0,  "max": 45.0},
}

ESTADO_MULT = {
    "Nuevo con etiquetas":  1.6,
    "Nuevo sin etiquetas":  1.35,
    "Muy bueno":            1.0,
    "Bueno":                0.8,
    "Satisfactorio":        0.55,
}

TASA_VENTA = {
    "Nuevo con etiquetas":  0.88,
    "Nuevo sin etiquetas":  0.82,
    "Muy bueno":            0.72,
    "Bueno":                0.58,
    "Satisfactorio":        0.38,
}

def cargar_precios_csv(archivo):
    try:
        df = pd.read_csv(archivo)
        
        # Detectar columna de precio automáticamente
        if "precio_num" in df.columns:
            df["precio_final"] = pd.to_numeric(df["precio_num"], errors="coerce")
        elif "precio_raw" in df.columns:
            df["precio_final"] = (
                df["precio_raw"]
                .astype(str)
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

def calcular_lote(marcas_lote, kg_total, precio_kg, precios):
    coste = kg_total * precio_kg
    ingresos = 0.0
    piezas_totales = 0
    piezas_vendidas = 0
    desglose = []

    for row in marcas_lote:
        marca = row["marca"]
        n = row["n"]
        estado = row["estado"]
        p = precios.get(marca)
        if not p:
            continue
        mult = ESTADO_MULT.get(estado, 1.0)
        tasa = TASA_VENTA.get(estado, 0.7)
        precio_venta = round(p["med"] * mult, 2)
        vendidas = round(n * tasa)
        ing = round(vendidas * precio_venta, 2)
        ingresos += ing
        piezas_totales += n
        piezas_vendidas += vendidas
        desglose.append({
            "Marca": marca, "Piezas": n, "Estado": estado,
            "Precio venta est.": f"{precio_venta:.2f} €",
            "Tasa venta": f"{int(tasa*100)}%",
            "Vendidas": vendidas,
            "Ingresos est.": f"{ing:.2f} €",
        })

    beneficio = round(ingresos - coste, 2)
    roi = round((beneficio / coste) * 100, 1) if coste > 0 else 0
    margen = round((beneficio / ingresos) * 100, 1) if ingresos > 0 else 0
    precio_max_kg = round((ingresos * 0.5) / kg_total, 2) if kg_total > 0 else 0

    return {
        "coste": coste, "ingresos": round(ingresos, 2),
        "beneficio": beneficio, "roi": roi, "margen": margen,
        "precio_max_kg": precio_max_kg,
        "piezas_totales": piezas_totales,
        "piezas_vendidas": piezas_vendidas,
        "desglose": desglose,
    }

def llamar_agente(api_key, resultado, marcas_lote, kg_total, precio_kg, precios):
    contexto_precios = "\n".join([
        f"- {m}: precio mediano {d['med']}€, rango {d['min']}–{d['max']}€"
        for m, d in precios.items()
    ])
    composicion = "\n".join([
        f"  · {r['marca']} ({r['n']} piezas, estado: {r['estado']})"
        for r in marcas_lote
    ])
    prompt = f"""Eres un experto en compraventa de ropa de segunda mano en Vinted España, especializado en lotes por kilos.

DATOS REALES DEL MERCADO (scraping Vinted.es):
{contexto_precios}

LOTE A EVALUAR:
- Peso total: {kg_total} kg
- Precio pagado: {precio_kg} €/kg
- Coste total: {resultado['coste']:.2f} €
- Composición:
{composicion}

ANÁLISIS CALCULADO:
- Ingresos estimados: {resultado['ingresos']:.2f} €
- Beneficio neto: {resultado['beneficio']:.2f} €
- ROI: {resultado['roi']}%
- Precio máximo seguro: {resultado['precio_max_kg']} €/kg
- Piezas estimadas vendibles: {resultado['piezas_vendidas']}/{resultado['piezas_totales']}

Dame un análisis experto en español que incluya:
1. Veredicto claro (comprar / no comprar / negociar precio)
2. Por qué en base a los datos reales del mercado
3. Qué marcas son las más valiosas y cuáles lastran el margen
4. Consejo de precio máximo a negociar si el ROI es bajo
5. Un riesgo clave con este lote

Sé directo, usa números concretos, máximo 200 palabras."""

    with st.spinner("El agente IA está analizando el lote..."):
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
    return response.json()["content"][0]["text"]


# ── UI ───────────────────────────────────────────────────────

st.title("👕 Agente Vinted — Evaluador de Lotes")
st.caption("Decide si un lote de ropa por kilos vale la pena antes de comprarlo")

with st.sidebar:
    st.header("Configuración")
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    if api_key:
        st.success("API Key cargada correctamente")
    else:
        st.warning("API Key no encontrada en secrets")

    st.divider()
    st.subheader("Actualizar precios")
    st.caption("Sube el CSV generado por el script R de scraping")
    csv_file = st.file_uploader("vinted_premium_YYYYMMDD.csv", type="csv")

    precios_activos = PRECIOS_BASE.copy()
    df_csv = None
    if csv_file:
        nuevos, df_csv = cargar_precios_csv(csv_file)
        if nuevos:
            precios_activos.update(nuevos)
            st.success(f"Precios actualizados con {len(nuevos)} marcas del CSV")

    st.divider()
    st.caption("Precios activos en el agente:")
    for m, d in sorted(precios_activos.items(), key=lambda x: -x[1]["med"]):
        st.caption(f"**{m}**: {d['med']}€ med.")

st.subheader("Parámetros del lote")
col1, col2 = st.columns(2)
with col1:
    kg_total = st.number_input("Peso total (kg)", min_value=1, max_value=500, value=20)
with col2:
    precio_kg = st.number_input("Precio pagado (€/kg)", min_value=0.5, max_value=50.0,
                                 value=5.0, step=0.5)

st.subheader("Composición del lote")
st.caption("Añade las marcas que el vendedor dice que hay en el lote")

if "marcas_lote" not in st.session_state:
    st.session_state.marcas_lote = [
        {"marca": "Ralph Lauren", "n": 5, "estado": "Muy bueno"}
    ]

marcas_disponibles = list(precios_activos.keys())
estados_disponibles = list(ESTADO_MULT.keys())

for i, row in enumerate(st.session_state.marcas_lote):
    c1, c2, c3, c4 = st.columns([3, 1, 2, 0.5])
    with c1:
        marca = st.selectbox("Marca", marcas_disponibles,
                              index=marcas_disponibles.index(row["marca"]) if row["marca"] in marcas_disponibles else 0,
                              key=f"marca_{i}", label_visibility="collapsed")
    with c2:
        n = st.number_input("Piezas", min_value=1, max_value=200, value=row["n"],
                             key=f"n_{i}", label_visibility="collapsed")
    with c3:
        estado = st.selectbox("Estado", estados_disponibles,
                               index=estados_disponibles.index(row["estado"]) if row["estado"] in estados_disponibles else 2,
                               key=f"estado_{i}", label_visibility="collapsed")
    with c4:
        if st.button("✕", key=f"del_{i}") and len(st.session_state.marcas_lote) > 1:
            st.session_state.marcas_lote.pop(i)
            st.rerun()

    st.session_state.marcas_lote[i] = {"marca": marca, "n": n, "estado": estado}

if st.button("+ Añadir marca"):
    st.session_state.marcas_lote.append({"marca": "Lacoste", "n": 3, "estado": "Muy bueno"})
    st.rerun()

st.divider()

if st.button("🔍 Evaluar lote", type="primary", use_container_width=True):
    resultado = calcular_lote(
        st.session_state.marcas_lote, kg_total, precio_kg, precios_activos
    )

    st.subheader("Resultado del análisis")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Inversión total",    f"{resultado['coste']:.2f} €")
    k2.metric("Ingresos estimados", f"{resultado['ingresos']:.2f} €",
              delta=f"+{resultado['beneficio']:.2f} €")
    k3.metric("ROI",                f"{resultado['roi']}%")
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

    st.subheader("Desglose por marca")
    st.dataframe(pd.DataFrame(resultado["desglose"]), use_container_width=True, hide_index=True)

    st.subheader("🤖 Análisis del Agente IA")
    if not api_key:
        st.info("API Key no encontrada. Añádela en Advanced Settings → Secrets.")
    else:
        analisis = llamar_agente(
            api_key, resultado,
            st.session_state.marcas_lote,
            kg_total, precio_kg, precios_activos
        )
        st.markdown(analisis)

if df_csv is not None:
    with st.expander("Ver datos del CSV cargado"):
        st.dataframe(df_csv.head(50), use_container_width=True)
