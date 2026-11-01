"""
Painel web do Sistema ITR (Etapa 12), em Streamlit.

Lê os mesmos arquivos Parquet do modelo para o Power BI e aplica as mesmas regras das medidas DAX.
A lógica e os números ficam em src/painel_dados.py; este arquivo só monta a tela.

Uso:
    streamlit run app/painel.py
"""
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import painel_dados as pdados  # noqa: E402

st.set_page_config(page_title="Orbe Suprimentos · ITR 3T26", layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------- identidade visual
# Paleta: azul royal #20309A, branco #FFFFFF e vermelho tomate #B8232B, com tons derivados.
AZUL, AZUL_MEDIO, AZUL_CLARO, AZUL_PALIDO = "#20309A", "#2a5bd7", "#79a5f0", "#d9e6fc"
TINTA, SUAVE, GRADE = "#0f1b3d", "#5b6888", "#e3e9f3"
VERMELHO, VERMELHO_CLARO = "#B8232B", "#e2878c"
CINZA = "#a9b3c7"
PALETA = [AZUL, AZUL_MEDIO, AZUL_CLARO, VERMELHO, VERMELHO_CLARO, "#5b6888", CINZA]
FONTE = "Manrope, Segoe UI, Arial, sans-serif"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Sora:wght@600;700&display=swap');

:root {{ --azul-medio:{AZUL_MEDIO}; --azul:{AZUL}; --azul-palido:{AZUL_PALIDO}; --tinta:{TINTA}; --suave:{SUAVE};
        --fundo:#f2f6fb; --cartao:#ffffff; --lateral:#0e1d4f; }}

html, body, .stApp, .stMarkdown, button, input, textarea, select {{ font-family: 'Manrope', 'Segoe UI', sans-serif; }}
.stApp {{ background: var(--fundo); color: var(--tinta); }}
header[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer {{ visibility: hidden; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }}

/* menu lateral escuro */
section[data-testid="stSidebar"] {{ background: var(--lateral); }}
section[data-testid="stSidebar"] * {{ color: #d6e2f7; }}
section[data-testid="stSidebar"] div[role="radiogroup"] {{ gap: 4px; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label {{ padding: 10px 14px; border-radius: 14px; margin: 0;
    width: 100%; transition: background .15s; cursor: pointer; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {{ display: none; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {{ background: rgba(255,255,255,.06); }}
section[data-testid="stSidebar"] div[role="radiogroup"] label[data-selected="true"],
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {{ background: linear-gradient(135deg, {AZUL}, {AZUL_MEDIO}); }}
section[data-testid="stSidebar"] div[role="radiogroup"] label[data-selected="true"] *,
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) * {{ color: #fff; font-weight: 700; }}
section[data-testid="stSidebar"] div[role="radiogroup"] label p {{ font-size: 15px; }}
.marca {{ display:flex; align-items:center; gap:12px; margin: 4px 0 26px; }}
.marca-logo {{ width:42px; height:42px; border-radius:13px; background: linear-gradient(135deg, {AZUL_CLARO}, {AZUL});
    display:flex; align-items:center; justify-content:center; font-family:'Sora',sans-serif; font-weight:700; color:#fff !important; font-size:20px; }}
.marca-nome {{ font-family:'Sora',sans-serif; font-weight:700; font-size:17px; color:#fff !important; line-height:1.1; }}
.marca-sub {{ font-size:12px; color:#9fb8ea !important; }}
.lateral-rodape {{ margin-top: 28px; padding: 14px; border-radius: 16px; background: rgba(255,255,255,.05); font-size: 12.5px; line-height: 1.5; }}
.lateral-rodape b {{ color: #fff !important; }}
.ponto {{ display:inline-block; width:8px; height:8px; border-radius:50%; background:{AZUL_CLARO}; margin-right:6px; }}

/* cabeçalho de página */
.cabecalho h1 {{ font-family:'Sora',sans-serif; font-size: 34px; font-weight: 700; margin: 0; padding: 0; color: var(--tinta); letter-spacing: -.01em; }}
.cabecalho p {{ margin: 4px 0 0; color: var(--suave); font-size: 14.5px; }}

/* cartões: o st.container(border=True) que começa com um título de cartão vira cartão branco */
div[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .titulo-cartao) {{ padding: 18px 20px 12px; background: var(--cartao); border: none !important; border-radius: 24px;
    box-shadow: 0 1px 2px rgba(18,26,63,.04), 0 8px 24px rgba(18,26,63,.06); }}
.titulo-cartao {{ display:flex; justify-content:space-between; align-items:baseline; gap: 12px; font-weight:700; font-size:16px; color:var(--tinta); margin: 2px 0 2px; }}
.titulo-cartao span {{ font-weight:500; font-size:12.5px; color:var(--suave); text-align: right; }}

/* cartão de destaque em degradê */
.hero {{ border-radius: 26px; padding: 26px 28px 22px; color: #fff; min-height: 360px;
    background: radial-gradient(120% 140% at 100% 0%, {AZUL_CLARO} 0%, rgba(121,165,240,0) 55%), linear-gradient(135deg, {AZUL} 0%, {AZUL_MEDIO} 100%);
    box-shadow: 0 18px 40px rgba(32,48,154,.30); display:flex; flex-direction:column; gap: 10px; }}
.hero * {{ color: #fff; }}
.hero-topo {{ display:flex; justify-content:space-between; align-items:center; gap: 8px; flex-wrap: wrap; font-size: 15px; opacity:.95; }}
.hero-valor {{ font-family:'Sora',sans-serif; font-size: 46px; font-weight: 700; letter-spacing:-.02em; line-height:1.05; }}
.hero-valor small {{ font-size: 18px; font-weight: 600; opacity: .85; margin-left: 6px; }}
.hero-rodape {{ display:grid; grid-template-columns: repeat(3, 1fr); margin-top: auto; }}
.hero-rodape div {{ padding: 0 14px; border-left: 1px dashed rgba(255,255,255,.45); }}
.hero-rodape div:first-child {{ padding-left: 0; border-left: none; }}
.hero-rodape span {{ display:block; font-size: 12.5px; opacity:.85; }}
.hero-rodape b {{ font-size: 21px; font-weight: 700; }}
.pilula {{ display:inline-flex; align-items:center; gap:4px; padding: 3px 10px; border-radius: 999px; font-size: 12.5px; font-weight: 700; white-space: nowrap; }}
.pilula.claro {{ background: rgba(255,255,255,.22); }}
.pilula.sobe {{ background: #e1eafc; color: #20309A; }}
.pilula.desce {{ background: #f8e1e2; color: #B8232B; }}
.pilula.neutro {{ background: #ebeff6; color: var(--suave); }}

/* cartões de indicador */
.kpi {{ display:flex; gap: 12px; align-items:center; padding: 14px 16px; background: var(--cartao); border-radius: 20px;
    box-shadow: 0 1px 2px rgba(18,26,63,.04), 0 8px 24px rgba(18,26,63,.06); height: 112px; box-sizing: border-box; overflow: hidden; }}
.kpi-selo {{ flex: 0 0 auto; min-width: 48px; height: 48px; border-radius: 14px; background: var(--azul-palido); color: var(--azul);
    display:flex; align-items:center; justify-content:center; font-family:'Sora',sans-serif; font-weight:700; font-size: 14px; padding: 0 6px; }}
.kpi-selo.escuro {{ background: var(--tinta); color: #fff; }}
.kpi-selo.vermelho {{ background: #f8e1e2; color: #B8232B; }}
.kpi-texto {{ min-width: 0; flex: 1; }}
.kpi-rotulo {{ font-size: 12.5px; color: var(--suave); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.kpi-valor {{ font-family:'Sora',sans-serif; font-size: 22px; font-weight: 700; color: var(--tinta); line-height: 1.25; }}
.kpi-detalhe {{ font-size: 12px; color: var(--suave); margin-top: 1px; line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
.barra {{ height: 6px; border-radius: 999px; background: #e5ebf5; margin-top: 6px; overflow: hidden; }}
.barra > i {{ display:block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, {AZUL}, {AZUL_CLARO}); }}
.espaco {{ height: 12px; }}

/* tabelas próprias */
.rolagem {{ overflow-x: auto; }}
table.lista {{ width:100%; border-collapse: collapse; font-size: 14px; }}
table.lista th {{ text-align:left; font-size: 12px; color: var(--suave); font-weight: 600; padding: 8px 10px; border-bottom: 1px solid {GRADE}; }}
table.lista td {{ padding: 11px 10px; border-bottom: 1px solid {GRADE}; color: var(--tinta); }}
table.lista tr:last-child td {{ border-bottom: none; }}
table.lista td.num {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; }}
.codigo {{ font-family: 'Sora', sans-serif; font-size: 12px; font-weight: 600; color: var(--azul); background: #e3ecfc; padding: 3px 8px; border-radius: 8px; }}
.legenda-rosca {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 14px; margin: 2px 2px 12px; }}
.legenda-rosca div {{ display:flex; align-items:center; gap: 7px; font-size: 12.5px; color: var(--tinta); min-width: 0; }}
.legenda-rosca i {{ flex: 0 0 10px; height: 10px; border-radius: 50%; }}
.legenda-rosca span {{ flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.legenda-rosca b {{ font-variant-numeric: tabular-nums; }}
table.lista, table.lista tr, table.lista th, table.lista td {{ border-left: none !important; border-right: none !important; border-top: none !important; }}
table.lista {{ border: none !important; }}
.legenda-nota {{ font-size: 12.5px; color: var(--suave); }}

/* controles */
.stDownloadButton button {{ border-radius: 14px; border: none; background: linear-gradient(135deg, {AZUL}, {AZUL_MEDIO}); color: #fff; font-weight: 700; padding: 10px 18px; }}
.stDownloadButton button:hover, .stDownloadButton button:focus {{ color: #fff; filter: brightness(1.05); }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- formatação
def br(numero: float, casas: int = 0) -> str:
    return f"{numero:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mil(valor) -> str:
    return "–" if valor is None else br(valor / 1000)


def pct(valor, casas: int = 1) -> str:
    return "n.d." if valor is None or pd.isna(valor) else br(valor * 100, casas) + "%"


def pilula_variacao(var, texto: str, fundo_claro: bool = False) -> str:
    if var is None:
        return f'<span class="pilula {"claro" if fundo_claro else "neutro"}">sem base de comparação</span>'
    seta, classe = ("▲", "sobe") if var >= 0 else ("▼", "desce")
    return f'<span class="pilula {"claro" if fundo_claro else classe}">{seta} {pct(abs(var))} {texto}</span>'


def kpi(rotulo, valor, detalhe="", selo="R$", tom="", barra=None) -> str:
    trilho = f'<div class="barra"><i style="width:{max(0.0, min(barra, 1.0)) * 100:.0f}%"></i></div>' if barra is not None else ""
    return (f'<div class="kpi"><div class="kpi-selo {tom}">{selo}</div><div class="kpi-texto">'
            f'<div class="kpi-rotulo">{rotulo}</div><div class="kpi-valor">{valor}</div>'
            f'<div class="kpi-detalhe">{detalhe}</div>{trilho}</div></div>')


def html(texto: str) -> None:
    st.markdown(texto, unsafe_allow_html=True)


def linha_de_kpis(cartoes: list[str]) -> None:
    for coluna, cartao in zip(st.columns(len(cartoes), gap="medium"), cartoes):
        coluna.markdown(cartao, unsafe_allow_html=True)
    html('<div class="espaco"></div>')


def titulo_cartao(titulo: str, nota: str = "") -> None:
    html(f'<div class="titulo-cartao">{titulo}<span>{nota}</span></div>')


def cabecalho(titulo: str, subtitulo: str):
    """Título à esquerda; devolve a coluna da direita para o filtro de período."""
    esquerda, direita = st.columns([1.2, 1], vertical_alignment="bottom")
    esquerda.markdown(f'<div class="cabecalho"><h1>{titulo}</h1><p>{subtitulo}</p></div>', unsafe_allow_html=True)
    return direita


def sparkline(valores: list[float], destaque: int, largura=520, altura=90) -> str:
    lo, hi = min(valores), max(valores)
    xs = [i * largura / (len(valores) - 1) for i in range(len(valores))]
    ys = [altura - 8 - (v - lo) / ((hi - lo) or 1) * (altura - 24) for v in valores]
    pontos = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (f'<svg viewBox="0 0 {largura} {altura}" width="100%" height="{altura}" preserveAspectRatio="none">'
            f'<defs><linearGradient id="spark" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".35"/>'
            f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="0,{altura} {pontos} {largura},{altura}" fill="url(#spark)"/>'
            f'<polyline points="{pontos}" fill="none" stroke="#fff" stroke-width="2.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{xs[destaque]:.1f}" cy="{ys[destaque]:.1f}" r="5" fill="#fff"/></svg>')


# ---------------------------------------------------------------- gráficos (Altair)
MILHAR = "replace(format(datum.value / 1000, ',.0f'), ',', '.')"  # eixo em R$ mil, com ponto no milhar


def mostrar(grafico, altura=280) -> None:
    grafico = (grafico.properties(height=altura, background="transparent")
               .configure_view(stroke=None)
               .configure_axis(labelFont=FONTE, labelColor=SUAVE, labelFontSize=12, gridColor=GRADE, domain=False,
                               tickColor="transparent", labelPadding=6)
               .configure_legend(labelFont=FONTE, labelColor=TINTA, labelFontSize=12.5, orient="top", title=None,
                                 symbolType="circle", symbolSize=110)
               .configure_text(font=FONTE))
    st.altair_chart(grafico, width="stretch")


def eixo_trimestre():
    return alt.X("trimestre:N", sort=TRIS, title=None, axis=alt.Axis(labelAngle=0, grid=False))


def barras_trimestre(df, coluna, destaque):
    base = alt.Chart(df).transform_calculate(
        rotulo=f"replace(format(datum['{coluna}'] / 1000, ',.0f'), ',', '.')").encode(x=eixo_trimestre())
    barras = base.mark_bar(cornerRadiusTopLeft=10, cornerRadiusTopRight=10, size=34).encode(
        y=alt.Y(f"{coluna}:Q", title=None, axis=alt.Axis(labelExpr=MILHAR, tickCount=4)),
        color=alt.condition(alt.datum.trimestre == destaque, alt.value(AZUL), alt.value(AZUL_PALIDO)),
        tooltip=[alt.Tooltip("trimestre:N", title="Trimestre"), alt.Tooltip("rotulo:N", title="R$ mil")])
    texto = base.transform_filter(alt.datum.trimestre == destaque).mark_text(
        dy=-10, fontWeight=700, color=TINTA, fontSize=12).encode(y=f"{coluna}:Q", text="rotulo:N")
    return alt.layer(barras, texto)


def linhas(df, cores: dict, formato=".0%", titulo_valor="Valor"):
    return alt.Chart(df).mark_line(point=alt.OverlayMarkDef(size=60, filled=True), strokeWidth=3,
                                   interpolate="monotone").encode(
        x=eixo_trimestre(),
        y=alt.Y("valor:Q", title=None, axis=alt.Axis(format=formato, tickCount=5)),
        color=alt.Color("serie:N", scale=alt.Scale(domain=list(cores), range=list(cores.values()))),
        tooltip=["trimestre:N", alt.Tooltip("serie:N", title="Série"),
                 alt.Tooltip("valor:Q", title=titulo_valor, format=formato)])


def barras_agrupadas(df, cores: dict):
    return alt.Chart(df).mark_bar(cornerRadius=6, size=20).encode(
        x=eixo_trimestre(),
        xOffset=alt.XOffset("serie:N", sort=list(cores)),
        y=alt.Y("valor:Q", title=None, axis=alt.Axis(labelExpr=MILHAR, tickCount=5)),
        color=alt.Color("serie:N", scale=alt.Scale(domain=list(cores), range=list(cores.values()))),
        tooltip=["trimestre:N", alt.Tooltip("serie:N", title="Série"), alt.Tooltip("valor:Q", title="R$", format=",.0f")])


def rosca(df, centro_valor: str, centro_rotulo: str, cores=None, unidade="R$ mil", altura=230) -> None:
    """Gráfico de rosca com o total no centro e uma legenda própria, com o percentual de cada parte."""
    pequenas = df.participacao < 0.02
    if pequenas.sum() > 1:  # fatias finas não se leem: viram uma só
        demais = pd.DataFrame([{"item": "Demais itens", "valor": df.valor[pequenas].sum(),
                                "participacao": df.participacao[pequenas].sum()}])
        df = pd.concat([df[~pequenas][["item", "valor", "participacao"]], demais], ignore_index=True)
    df = df.reset_index(drop=True).assign(ordem=lambda x: range(len(x)), valor_mil=lambda x: x.valor / 1000)
    cores = (cores or PALETA)[: len(df)]
    if len(cores) < len(df):
        cores = cores + [CINZA] * (len(df) - len(cores))
    if df.item.iloc[-1] == "Demais itens":
        cores = cores[:-1] + [CINZA]
    raio = altura / 2 - 18
    arco = alt.Chart(df).mark_arc(innerRadius=raio * 0.68, outerRadius=raio, cornerRadius=4, padAngle=0.02).encode(
        theta=alt.Theta("valor:Q", stack=True),
        color=alt.Color("item:N", scale=alt.Scale(domain=df.item.tolist(), range=cores), legend=None),
        order=alt.Order("ordem:Q"),
        tooltip=[alt.Tooltip("item:N", title="Item"), alt.Tooltip("participacao:Q", title="Participação", format=".1%"),
                 alt.Tooltip("valor_mil:Q", title=unidade, format=",.0f")])
    valor = alt.Chart(pd.DataFrame({"t": [centro_valor]})).mark_text(
        fontSize=24, fontWeight=800, color=TINTA, dy=-8).encode(text="t:N")
    rotulo = alt.Chart(pd.DataFrame({"t": [centro_rotulo]})).mark_text(fontSize=12, color=SUAVE, dy=16).encode(text="t:N")
    mostrar(alt.layer(arco, valor, rotulo), altura)
    itens = "".join(f'<div><i style="background:{c}"></i><span>{n}</span><b>{pct(p_)}</b></div>'
                    for n, p_, c in zip(df.item, df.participacao, cores))
    html(f'<div class="legenda-rosca">{itens}</div>')


ROTULO_CURTO = {"Receita líquida": "Receita", "Custo das vendas": "Custo", "Despesas com vendas": "Vendas",
                "Despesas gerais": "Gerais", "Perda de crédito": "Perdas", "Outras operacionais": "Outras",
                "Resultado financeiro": "Financeiro", "IR e CSLL": "IR/CSLL", "Lucro líquido": "Lucro"}


def quebrar(nome: str) -> str:
    """Divide o rótulo em duas linhas equilibradas (o eixo do Vega quebra no '|')."""
    palavras = nome.split()
    if len(palavras) < 2:
        return nome
    melhor = min(range(1, len(palavras)),
                 key=lambda k: abs(len(" ".join(palavras[:k])) - len(" ".join(palavras[k:]))))
    return " ".join(palavras[:melhor]) + "|" + " ".join(palavras[melhor:])


def cascata(df, unidade="R$ mil", divisor=1000, curto=False):
    """Gráfico de cascata: cada barra vai de `inicio` a `fim`; totais em azul royal, reduções em vermelho."""
    df = df.copy()
    df["cor"] = ["total" if t == "total" else ("positivo" if v >= 0 else "negativo") for t, v in zip(df.tipo, df.valor)]
    df["texto"] = [("+" if (t != "total" and v > 0) else "") + br(v / divisor) for t, v in zip(df.tipo, df.valor)]
    df["topo"] = df[["inicio", "fim"]].max(axis=1)
    df["eixo"] = [ROTULO_CURTO.get(e, quebrar(e)) if curto else quebrar(e) for e in df.etapa]
    eixo_y = alt.Axis(labelExpr=MILHAR, tickCount=5) if divisor == 1000 else alt.Axis(tickCount=5)
    base = alt.Chart(df).encode(x=alt.X("eixo:N", sort=df.eixo.tolist(), title=None,
                                        axis=alt.Axis(labelAngle=0, labelOverlap=False, grid=False, labelFontSize=11.5,
                                                      labelExpr="split(datum.label, '|')", labelLineHeight=14)))
    barras = base.mark_bar(cornerRadius=8, size=38).encode(
        y=alt.Y("inicio:Q", title=None, axis=eixo_y), y2="fim:Q",
        color=alt.Color("cor:N", legend=None, scale=alt.Scale(domain=["total", "positivo", "negativo"],
                                                              range=[AZUL, AZUL_CLARO, VERMELHO])),
        tooltip=[alt.Tooltip("etapa:N", title="Etapa"), alt.Tooltip("texto:N", title=unidade)])
    texto = base.mark_text(dy=-9, fontWeight=700, fontSize=12, color=TINTA).encode(y="topo:Q", text="texto:N")
    return alt.layer(barras, texto)


# ---------------------------------------------------------------- dados
@st.cache_data
def carregar():
    return pdados.carregar()


try:
    d = carregar()
except FileNotFoundError as erro:
    st.error(str(erro))
    st.stop()

TRIS = d.trimestres
ULTIMO = TRIS[-1]
q = d.t["fato_qualidade"]
ERROS = int((q.status == "erro").sum())
APROVADAS = int((q.status == "aprovado").sum())


def escolher_trimestre(lugar, chave: str) -> str:
    escolha = lugar.segmented_control("Trimestre", TRIS, default=ULTIMO, key=chave)
    return escolha or ULTIMO


def escolher_periodo(lugar, chave: str) -> list[str]:
    inicio, fim = lugar.select_slider("Período", options=TRIS, value=(TRIS[-3], ULTIMO), key=chave)
    return TRIS[TRIS.index(inicio): TRIS.index(fim) + 1]


def soma(codigo: str, tris: list[str]) -> float:
    return pdados.valor_df(d, codigo, tris) or 0.0


# ---------------------------------------------------------------- menu lateral
PAGINAS = ["Visão geral", "Resultado", "Balanço", "Fluxo de caixa", "Capital de giro", "Demonstrações",
           "Central de qualidade", "Baixar o ITR"]
with st.sidebar:
    html('<div class="marca"><div class="marca-logo">O</div><div><div class="marca-nome">Orbe Suprimentos</div>'
         '<div class="marca-sub">Informações trimestrais · 3T26</div></div></div>')
    pagina = st.radio("Menu", PAGINAS, label_visibility="collapsed", key="pagina")
    html(f'<div class="lateral-rodape"><span class="ponto"></span><b>Publicação {"liberada" if ERROS == 0 else "bloqueada"}</b><br>'
         f'{APROVADAS} de {len(q)} verificações aprovadas<br>'
         f'<span style="opacity:.7">Valores em R$ mil · empresa e números fictícios</span><br><br>'
         f'<a href="https://github.com/robsousax/sistema-itr" style="color:{AZUL_CLARO} !important">Código no GitHub ↗</a></div>')


# ---------------------------------------------------------------- páginas
def visao_geral():
    tri = escolher_trimestre(cabecalho("Visão geral", "Desempenho trimestral da Orbe Suprimentos S.A. · R$ mil"), "tri_visao")
    k = pdados.destaques(d, tri)
    ant = pdados.ano_anterior(tri)
    serie = pdados.serie_resultado(d)

    a, b, c = st.columns([1.3, 1.2, 1], gap="medium")
    with a:
        html(f'<div class="hero"><div class="hero-topo"><span>Receita líquida · {tri}</span>'
             f'{pilula_variacao(k["var_receita"], f"sobre {ant}", fundo_claro=True)}</div>'
             f'<div class="hero-valor">{mil(k["receita"])}<small>R$ mil</small></div>'
             f'{sparkline(serie["Receita líquida"].tolist(), TRIS.index(tri))}'
             f'<div class="hero-rodape"><div><span>Margem bruta</span><b>{pct(k["margem_bruta"])}</b></div>'
             f'<div><span>Margem EBITDA</span><b>{pct(k["margem_ebitda"])}</b></div>'
             f'<div><span>Margem líquida</span><b>{pct(k["margem_liquida"])}</b></div></div></div>')
    with b:
        with st.container(border=True):
            titulo_cartao("Composição do ativo", tri)
            comp = pdados.composicao_ativo(d, tri).query("valor > 0")
            rosca(comp, mil(pdados.v(d, "1", tri)), "ativo total", altura=210)
    with c:
        html(kpi("EBITDA", mil(k["ebitda"]), f"Margem de {pct(k['margem_ebitda'])} · Res. CVM 156", "EB"))
        html('<div class="espaco"></div>')
        html(kpi("Lucro líquido", mil(k["lucro"]), pilula_variacao(k["var_lucro"], f"sobre {ant}"), "LL", "escuro"))
        html('<div class="espaco"></div>')
        caixa_liquido = k["divida_liquida"] < 0
        html(kpi("Caixa líquido" if caixa_liquido else "Dívida líquida", mil(abs(k["divida_liquida"])),
                 f"Caixa {mil(k['caixa'])} · dívida {mil(k['caixa'] + k['divida_liquida'])}", "Cx"))

    html('<div class="espaco"></div>')
    e, f = st.columns([1.3, 2], gap="medium")
    with e:
        with st.container(border=True):
            titulo_cartao("Receita líquida por trimestre", "R$ mil")
            mostrar(barras_trimestre(serie, "Receita líquida", tri), 262)
    with f:
        with st.container(border=True):
            titulo_cartao(f"Da receita ao lucro · {tri}", "R$ mil")
            mostrar(cascata(pdados.cascata_resultado(d, [tri]), curto=True), 262)

    html('<div class="espaco"></div>')
    liq, ciclo, roe = (pdados.indicador(d, c_, tri) for c_ in ("liq_corrente", "ciclo_financeiro", "roe"))
    linha_de_kpis([
        kpi("Liquidez corrente", f"{br(liq, 2)}x" if liq else "n.d.", "Ativo circulante / passivo circulante", "x",
            barra=(liq or 0) / 3),
        kpi("Ciclo financeiro", f"{br(ciclo)} dias" if ciclo else "n.d.", "PMR + PME − PMP", "d", barra=(ciclo or 0) / 120),
        kpi("ROE dos últimos 12 meses", pct(roe), "Lucro UDM / PL médio (n.d. antes de 4 trimestres)", "%", "vermelho",
            barra=(roe or 0) / 0.2),
    ])


def resultado():
    tris = escolher_periodo(cabecalho("Resultado", "DRE: receita, custos, despesas e margens · R$ mil"), "periodo_resultado")
    per = pdados.periodo(tris)
    receita, bruto, lucro = soma("3.01", tris), soma("3.03", tris), soma("3.11", tris)
    ebitda = sum(pdados.ebitda(d, t) for t in tris)
    linha_de_kpis([
        kpi("Receita líquida", mil(receita), per, "R$"),
        kpi("Resultado bruto", mil(bruto), f"Margem de {pct(bruto / receita)}", "RB"),
        kpi("EBITDA", mil(ebitda), f"Margem de {pct(ebitda / receita)}", "EB"),
        kpi("Lucro líquido", mil(lucro), f"Margem de {pct(lucro / receita)}", "LL", "escuro"),
    ])
    with st.container(border=True):
        titulo_cartao(f"Da receita ao lucro · {per}", "R$ mil")
        mostrar(cascata(pdados.cascata_resultado(d, tris)), 330)

    html('<div class="espaco"></div>')
    a, b = st.columns([1.5, 1], gap="medium")
    with a:
        with st.container(border=True):
            titulo_cartao("Margens por trimestre")
            serie = pdados.serie_resultado(d).melt("trimestre", ["Margem bruta", "Margem EBITDA", "Margem líquida"],
                                                   "serie", "valor")
            mostrar(linhas(serie, {"Margem bruta": AZUL, "Margem EBITDA": AZUL_CLARO, "Margem líquida": VERMELHO_CLARO}), 290)
    with b:
        with st.container(border=True):
            titulo_cartao("Para onde vai cada real de receita", per)
            itens = [("Custo das vendas", "3.02"), ("Despesas com vendas", "3.04.01"),
                     ("Despesas administrativas", "3.04.02"), ("Perda de crédito", "3.04.03"), ("IR e CSLL", "3.08")]
            df = pd.DataFrame([{"item": n, "valor": -soma(c_, tris)} for n, c_ in itens])
            df = pd.concat([df, pd.DataFrame([{"item": "Lucro e demais itens", "valor": receita - df.valor.sum()}])],
                           ignore_index=True)
            df["participacao"] = df.valor / receita
            rosca(df, "100%", "da receita", [AZUL, AZUL_MEDIO, AZUL_CLARO, VERMELHO, VERMELHO_CLARO, AZUL_PALIDO], altura=290)


def balanco():
    tri = escolher_trimestre(cabecalho("Balanço patrimonial", "Composição do ativo, estrutura de capital e liquidez · R$ mil"),
                             "tri_balanco")
    ativo, pl = pdados.v(d, "1", tri), pdados.v(d, "2.03", tri)
    liq, seca = pdados.indicador(d, "liq_corrente", tri), pdados.indicador(d, "liq_seca", tri)
    linha_de_kpis([
        kpi("Ativo total", mil(ativo), f"30/09: fim do {tri}" if tri.startswith("3") else f"fim do {tri}", "AT"),
        kpi("Patrimônio líquido", mil(pl), f"{pct(pl / ativo)} do ativo", "PL", "escuro"),
        kpi("Liquidez corrente", f"{br(liq, 2)}x", "Ativo circulante / passivo circulante", "x", barra=liq / 3),
        kpi("Liquidez seca", f"{br(seca, 2)}x", "Sem estoques e despesas antecipadas", "x", barra=seca / 3),
    ])
    a, b = st.columns(2, gap="medium")
    with a:
        with st.container(border=True):
            titulo_cartao("Composição do ativo", tri)
            rosca(pdados.composicao_ativo(d, tri).query("valor > 0"), mil(ativo), "ativo total", altura=290)
    with b:
        with st.container(border=True):
            titulo_cartao("Estrutura de capital", tri)
            rosca(pdados.estrutura_capital(d, tri), pct(pl / ativo, 0), "capital próprio",
                  [VERMELHO, VERMELHO_CLARO, AZUL], altura=290)

    html('<div class="espaco"></div>')
    with st.container(border=True):
        titulo_cartao("Caixa, dívida bruta e patrimônio líquido", "R$ mil, no fim de cada trimestre")
        serie = pdados.serie_balanco(d).melt("trimestre", var_name="serie", value_name="valor")
        mostrar(barras_agrupadas(serie, {"Caixa e equivalentes": AZUL_MEDIO, "Dívida bruta": VERMELHO,
                                         "Patrimônio líquido": AZUL}), 300)


def fluxo_de_caixa():
    tris = escolher_periodo(cabecalho("Fluxo de caixa", "DFC pelo método indireto e distribuição do valor adicionado · R$ mil"),
                            "periodo_caixa")
    per = pdados.periodo(tris)
    fco, fci, fcf = soma("6.01", tris), soma("6.02", tris), soma("6.03", tris)
    linha_de_kpis([
        kpi("Caixa das operações", mil(fco), per, "OP"),
        kpi("Investimentos", mil(fci), "Imobilizado e intangível", "IN", "vermelho"),
        kpi("Financiamentos", mil(fcf), "Empréstimos, juros e dividendos", "FI"),
        kpi("Saldo final de caixa", mil(soma("6.05.02", tris)), f"Variação de {mil(fco + fci + fcf)} no período", "Cx", "escuro"),
    ])
    a, b = st.columns([1.5, 1], gap="medium")
    with a:
        with st.container(border=True):
            titulo_cartao(f"Ponte de caixa · {per}", "R$ mil")
            mostrar(cascata(pdados.ponte_caixa(d, tris)), 320)
    with b:
        with st.container(border=True):
            titulo_cartao("Distribuição do valor adicionado", f"DVA · {per}")
            dva = pdados.distribuicao_valor_adicionado(d, tris)
            rosca(dva, mil(dva.valor.sum()), "R$ mil distribuídos", [AZUL, VERMELHO, VERMELHO_CLARO, AZUL_CLARO], altura=262)

    html('<div class="espaco"></div>')
    with st.container(border=True):
        titulo_cartao("Caixa por atividade, trimestre a trimestre", "R$ mil")
        serie = pd.DataFrame([{"trimestre": t, "serie": n, "valor": pdados.v(d, c_, t)} for t in TRIS
                              for n, c_ in (("Operacional", "6.01"), ("Investimento", "6.02"), ("Financiamento", "6.03"))])
        mostrar(barras_agrupadas(serie, {"Operacional": AZUL, "Investimento": VERMELHO, "Financiamento": VERMELHO_CLARO}), 300)


def capital_de_giro():
    tri = escolher_trimestre(cabecalho("Capital de giro", "Prazos médios e ciclo financeiro, com saldos médios do trimestre"),
                             "tri_giro")
    ant = TRIS[TRIS.index(tri) - 1] if TRIS.index(tri) > 0 else None
    cartoes = []
    for cod, nome, selo, tom in (("pmr", "Recebimento", "PMR", ""), ("pme", "Estocagem", "PME", ""),
                                 ("pmp", "Pagamento", "PMP", "vermelho"), ("ciclo_financeiro", "Ciclo financeiro", "CF", "escuro")):
        atual = pdados.indicador(d, cod, tri)
        anterior = pdados.indicador(d, cod, ant) if ant else None
        detalhe = f"{'+' if atual - anterior > 0 else ''}{br(atual - anterior)} dias sobre {ant}" if (atual and anterior) else "dias"
        cartoes.append(kpi(nome, f"{br(atual)} dias" if atual else "n.d.", detalhe, selo, tom))
    linha_de_kpis(cartoes)

    a, b = st.columns([1.5, 1], gap="medium")
    with a:
        with st.container(border=True):
            titulo_cartao("Prazos médios por trimestre", "dias")
            serie = pdados.serie_indicador(d, {"pmr": "PMR", "pme": "PME", "pmp": "PMP"}).rename(columns={"indicador": "serie"})
            mostrar(linhas(serie, {"PMR": AZUL, "PME": AZUL_CLARO, "PMP": VERMELHO}, formato=".0f", titulo_valor="Dias"), 300)
    with b:
        with st.container(border=True):
            titulo_cartao("Como se forma o ciclo", f"dias · {tri}")
            pmr, pme, pmp = (pdados.indicador(d, c_, tri) or 0 for c_ in ("pmr", "pme", "pmp"))
            ciclo = pd.DataFrame([
                {"etapa": "Recebimento", "inicio": 0, "fim": pmr, "valor": pmr, "tipo": "passo"},
                {"etapa": "Estocagem", "inicio": pmr, "fim": pmr + pme, "valor": pme, "tipo": "passo"},
                {"etapa": "Pagamento", "inicio": pmr + pme, "fim": pmr + pme - pmp, "valor": -pmp, "tipo": "passo"},
                {"etapa": "Ciclo financeiro", "inicio": 0, "fim": pmr + pme - pmp, "valor": pmr + pme - pmp, "tipo": "total"}])
            mostrar(cascata(ciclo, unidade="dias", divisor=1), 300)


NOMES_CURTOS = {"BP": "Balanço", "DRE": "Resultado", "DRA": "Abrangente", "DFC": "Fluxo de caixa",
                "DVA": "Valor adicionado", "EBITDA": "EBITDA"}


def demonstracoes():
    tris = escolher_periodo(cabecalho("Demonstrações", "Linhas da CVM, trimestre a trimestre, com a coluna do período"),
                            "periodo_df")
    opcoes = pdados.demonstracoes(d)
    demo = st.segmented_control("Demonstração", [o[0] for o in opcoes], default="DRE",
                                format_func=NOMES_CURTOS.get, key="demo") or "DRE"
    tabela = pdados.matriz(d, demo, tris)
    with st.container(border=True):
        titulo_cartao(dict(opcoes)[demo], f"R$ mil · coluna Período = {pdados.periodo(tris)}")

        def destacar(linha):
            estilo = f"font-weight: 700; background-color: #edf2fc; color: {TINTA}" if tabela.destaque[linha.name] else ""
            return [estilo] * len(linha)

        visivel = tabela.drop(columns="destaque")
        st.dataframe(visivel.style.apply(destacar, axis=1).format(lambda x: "–" if pd.isna(x) else br(x),
                                                                  subset=tris + ["Período"]),
                     hide_index=True, height=min(40 + 35 * len(visivel), 1400))
    html('<p class="legenda-nota">Coluna Período: fluxos somam os trimestres, saldos de balanço ficam com o último '
         'e o saldo inicial de caixa fica com o primeiro (regra semiaditiva). De 1T26 a 3T26, é o 9M26 do ITR.</p>')


def qualidade():
    tri = escolher_trimestre(cabecalho("Central de qualidade", "20 verificações antes de publicar e conferências do painel"),
                             "tri_qualidade")
    linha_de_kpis([
        kpi("Publicação", "Liberada" if ERROS == 0 else "Bloqueada", f"Execução {d.run_id}", "✓",
            "escuro" if ERROS == 0 else "vermelho"),
        kpi("Aprovadas", f"{APROVADAS} de {len(q)}", "verificações", "OK"),
        kpi("Alertas", str(int((q.status == "alerta").sum())), "registrados, não bloqueiam", "!"),
        kpi("Erros", str(ERROS), "bloqueiam a publicação", "×", "vermelho"),
    ])
    ok_html = {True: '<span class="pilula sobe">OK</span>', False: '<span class="pilula desce">Diferença</span>'}
    classe = {"aprovado": "sobe", "alerta": "neutro", "erro": "desce"}
    a, b = st.columns([1, 1.6], gap="medium")
    with a:
        with st.container(border=True):
            titulo_cartao("Conferências do painel", f"{tri} · devem dar zero")
            conf = pdados.conferencias(d, tri)
            corpo = "".join(f'<tr><td>{nome}</td><td class="num">{br(dif, 2)}</td><td>{ok_html[bool(ok)]}</td></tr>'
                            for nome, dif, ok in conf.itertuples(index=False))
            html(f'<table class="lista"><tr><th>Conferência</th><th style="text-align:right">R$</th><th></th></tr>{corpo}</table>')
        html('<div class="espaco"></div>')
        with st.container(border=True):
            titulo_cartao("Verificações por nível")
            por_nivel = q.groupby("nivel_nome", sort=False).size().reset_index(name="quantidade")
            por_nivel = por_nivel.rename(columns={"nivel_nome": "item"}).assign(
                valor=lambda x: x.quantidade * 1000, participacao=lambda x: x.quantidade / x.quantidade.sum())
            rosca(por_nivel, str(len(q)), "verificações", [AZUL_CLARO, AZUL_MEDIO, AZUL],
                  unidade="Verificações", altura=230)
    with b:
        with st.container(border=True):
            titulo_cartao("As 20 verificações", f"execução {d.run_id}")
            corpo = "".join(f'<tr><td><span class="codigo">{r.codigo}</span></td><td>{r.nivel_nome}</td><td>{r.descricao}</td>'
                            f'<td><span class="pilula {classe[r.status]}">{r.status}</span></td></tr>' for r in q.itertuples())
            html(f'<div class="rolagem"><table class="lista"><tr><th>Código</th><th>Nível</th><th>Verificação</th>'
                 f'<th>Status</th></tr>{corpo}</table></div>')


def baixar():
    cabecalho("Baixar o ITR", "O ITR completo do 3T26, gerado pelo sistema")
    arquivos = (("ITR_Orbe_3T26.pdf", "application/pdf", "ITR em PDF",
                 "19 páginas: capa com destaques, comentário de desempenho, as demonstrações, 10 notas explicativas, "
                 "indicadores com a reconciliação do EBITDA e a página da Central de qualidade."),
                ("ITR_Orbe_3T26.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "ITR em Excel",
                 "14 abas, uma por peça. Valores exatos em reais, exibidos em R$ mil, com conferências por fórmula no pé "
                 "de cada demonstração."))
    for coluna, (nome, tipo, titulo, texto) in zip(st.columns(2, gap="medium"), arquivos):
        with coluna:
            with st.container(border=True):
                titulo_cartao(titulo)
                html(f'<p class="legenda-nota" style="font-size:14px">{texto}</p>')
                arquivo = RAIZ / "exemplos" / nome
                if arquivo.exists():
                    st.download_button(f"Baixar {nome}", arquivo.read_bytes(), file_name=nome, mime=tipo, key=nome)
    html('<p class="legenda-nota">Código, documentação e testes em '
         '<a href="https://github.com/robsousax/sistema-itr">github.com/robsousax/sistema-itr</a> · '
         f'dados: {d.pasta.relative_to(RAIZ).as_posix()}/</p>')


PAGINA = {"Visão geral": visao_geral, "Resultado": resultado, "Balanço": balanco, "Fluxo de caixa": fluxo_de_caixa,
          "Capital de giro": capital_de_giro, "Demonstrações": demonstracoes, "Central de qualidade": qualidade,
          "Baixar o ITR": baixar}
PAGINA[pagina]()
