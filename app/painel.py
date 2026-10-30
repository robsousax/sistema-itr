"""
Painel web do Sistema ITR (Etapa 12), em Streamlit.

Mostra os mesmos números do Power BI, lidos dos mesmos arquivos Parquet. A lógica fica em
src/painel_dados.py; este arquivo só monta a tela.

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

st.set_page_config(page_title="Orbe Suprimentos · ITR 3T26", layout="wide")

ACENTO, ACENTO2, ACENTO3, SUAVE = "#1f5f7a", "#8fb3c4", "#c98b2b", "#5b6672"


@st.cache_data
def carregar():
    return pdados.carregar()


def mil(valor) -> str:
    return "–" if valor is None else f"{valor / 1000:,.0f}".replace(",", ".")


def pct(valor, sinal=False) -> str:
    if valor is None:
        return "n.d."
    texto = f"{valor:+.1%}" if sinal else f"{valor:.1%}"
    return texto.replace(".", ",")


try:
    d = carregar()
except FileNotFoundError as erro:
    st.error(str(erro))
    st.stop()

TRIS = d.trimestres
EIXO_X = alt.X("trimestre:N", sort=TRIS, title=None, axis=alt.Axis(labelAngle=0))
MILHAR_BR = "replace(datum.label, ',', '.')"  # o Vega formata com vírgula; no Brasil o milhar é ponto

st.title("Orbe Suprimentos S.A.")
st.caption("Informações trimestrais (ITR) · valores em R$ mil · simulação acadêmica: empresa e números fictícios")

aba_visao, aba_df, aba_ind, aba_qual, aba_baixar = st.tabs(
    ["Visão geral", "Demonstrações", "Indicadores", "Qualidade", "Baixar o ITR"])

# ---------------------------------------------------------------- visão geral
with aba_visao:
    tri = st.selectbox("Trimestre", TRIS, index=len(TRIS) - 1, key="tri_visao")
    k = pdados.destaques(d, tri)
    ant = pdados.ano_anterior(tri)
    c = st.columns(3)
    c[0].metric("Receita líquida", mil(k["receita"]),
                f"{pct(k['var_receita'], True)} sobre {ant}" if k["var_receita"] is not None else None)
    c[1].metric("EBITDA", mil(k["ebitda"]))
    c[1].caption(f"Margem EBITDA de {pct(k['margem_ebitda'])}")
    c[2].metric("Lucro líquido", mil(k["lucro"]),
                f"{pct(k['var_lucro'], True)} sobre {ant}" if k["var_lucro"] is not None else None)
    c = st.columns(3)
    c[0].metric("Margem bruta", pct(k["margem_bruta"]))
    c[0].caption(f"Margem líquida de {pct(k['margem_liquida'])}")
    c[1].metric("Caixa e equivalentes", mil(k["caixa"]))
    c[1].caption(f"Patrimônio líquido de {mil(k['pl'])}")
    c[2].metric("Dívida líquida", mil(k["divida_liquida"]))
    c[2].caption("Negativa: a empresa tem mais caixa do que dívida" if k["divida_liquida"] < 0
                 else "Dívida maior que o caixa")

    serie = pdados.serie_resultado(d)
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Receita líquida e EBITDA por trimestre** (R$ mil)")
        barras = serie.melt("trimestre", ["Receita líquida", "EBITDA"], "Medida", "Valor")
        barras["Valor"] = barras.Valor / 1000
        st.altair_chart(alt.Chart(barras).mark_bar().encode(
            x=EIXO_X,
            xOffset=alt.XOffset("Medida:N", sort=["Receita líquida", "EBITDA"]),
            y=alt.Y("Valor:Q", title=None, axis=alt.Axis(format=",.0f", labelExpr=MILHAR_BR)),
            color=alt.Color("Medida:N", scale=alt.Scale(domain=["Receita líquida", "EBITDA"], range=[ACENTO, ACENTO3]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["trimestre", "Medida", alt.Tooltip("Valor:Q", format=",.0f")],
        ).properties(height=300), width="stretch")
    with g2:
        st.markdown("**Margens por trimestre**")
        margens = serie.melt("trimestre", ["Margem bruta", "Margem EBITDA", "Margem líquida"], "Margem", "Valor")
        st.altair_chart(alt.Chart(margens).mark_line(point=True).encode(
            x=EIXO_X,
            y=alt.Y("Valor:Q", title=None, axis=alt.Axis(format=".0%")),
            color=alt.Color("Margem:N", scale=alt.Scale(domain=["Margem bruta", "Margem EBITDA", "Margem líquida"],
                                                        range=[ACENTO, ACENTO3, ACENTO2]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["trimestre", "Margem", alt.Tooltip("Valor:Q", format=".1%")],
        ).properties(height=300), width="stretch")
    st.caption("EBITDA conforme a Resolução CVM 156: lucro líquido + IR e CSLL + resultado financeiro líquido "
               "+ depreciação e amortização.")

# ---------------------------------------------------------------- demonstrações
with aba_df:
    opcoes = pdados.demonstracoes(d)
    col1, col2 = st.columns([1, 2])
    demo = col1.selectbox("Demonstração", [o[0] for o in opcoes], index=1,
                          format_func=dict(opcoes).get, key="demo")
    tris = col2.multiselect("Trimestres", TRIS, default=TRIS[-3:], key="tris")
    tris = [t for t in TRIS if t in tris] or [TRIS[-1]]
    tabela = pdados.matriz(d, demo, tris)

    def destacar(linha):
        estilo = "font-weight: 600; background-color: rgba(31, 95, 122, 0.08)" if tabela.destaque[linha.name] else ""
        return [estilo] * len(linha)

    visivel = tabela.drop(columns="destaque")
    st.dataframe(
        visivel.style.apply(destacar, axis=1).format(lambda x: "–" if pd.isna(x) else f"{x:,.0f}".replace(",", "."),
                                                      subset=tris + ["Período"]),
        hide_index=True, height=min(38 + 35 * len(visivel), 1200))
    st.caption("Coluna Período: fluxos somam os trimestres escolhidos, saldos de balanço ficam com o último e o saldo "
               "inicial de caixa fica com o primeiro (a medida semiaditiva). Com 1T26, 2T26 e 3T26 ela é o 9M26 do ITR.")

# ---------------------------------------------------------------- indicadores
with aba_ind:
    ind = pdados.tabela_indicadores(d)
    st.dataframe(ind, hide_index=True, height=38 + 35 * len(ind),
                 column_config={"Fórmula": st.column_config.TextColumn(width="medium")})
    st.markdown("**Capital de giro** (dias)")
    prazos = pdados.serie_prazos(d)
    st.altair_chart(alt.Chart(prazos).mark_line(point=True).encode(
        x=EIXO_X,
        y=alt.Y("dias:Q", title=None),
        color=alt.Color("prazo:N", scale=alt.Scale(domain=["PMR", "PME", "PMP", "Ciclo financeiro"],
                                                   range=[ACENTO, ACENTO2, ACENTO3, SUAVE]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["trimestre", "prazo", alt.Tooltip("dias:Q", format=".0f")],
    ).properties(height=280), width="stretch")
    st.caption("Prazos médios com saldo médio do trimestre. UDM = últimos 12 meses: n.d. antes de existirem "
               "4 trimestres de história.")

# ---------------------------------------------------------------- qualidade
with aba_qual:
    q = d.t["fato_qualidade"]
    erros = int((q.status == "erro").sum())
    c = st.columns(4)
    c[0].metric("Publicação", "Liberada" if erros == 0 else "Bloqueada")
    c[1].metric("Aprovadas", f"{int((q.status == 'aprovado').sum())} de {len(q)}")
    c[2].metric("Alertas", int((q.status == "alerta").sum()))
    c[3].metric("Erros", erros)
    st.caption(f"Execução {d.run_id} da Central de qualidade, a mesma que liberou a exportação.")

    st.markdown("**Conferências do painel** (devem dar zero)")
    tri_q = st.selectbox("Trimestre", TRIS, index=len(TRIS) - 1, key="tri_qual")
    conf = pdados.conferencias(d, tri_q)
    conf["Diferença (R$)"] = conf["Diferença (R$)"].map(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    st.dataframe(conf, hide_index=True,
                 column_config={"OK": st.column_config.CheckboxColumn()})

    st.markdown("**As 20 verificações**")
    st.dataframe(q[["codigo", "nivel_nome", "descricao", "status"]].rename(
        columns={"codigo": "Código", "nivel_nome": "Nível", "descricao": "Verificação", "status": "Status"}),
        hide_index=True, height=38 + 35 * len(q))

# ---------------------------------------------------------------- downloads
with aba_baixar:
    st.markdown("O ITR completo do 3T26, gerado pelo sistema: demonstrações, notas explicativas, "
                "comentário de desempenho, indicadores e Central de qualidade.")
    for nome, tipo, rotulo in (("ITR_Orbe_3T26.pdf", "application/pdf", "Baixar o PDF (19 páginas)"),
                               ("ITR_Orbe_3T26.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                "Baixar o Excel (14 abas, com conferências por fórmula)")):
        arquivo = RAIZ / "exemplos" / nome
        if arquivo.exists():
            st.download_button(rotulo, arquivo.read_bytes(), file_name=nome, mime=tipo)
    st.markdown("Código, documentação e testes: [github.com/robsousax/sistema-itr]"
                "(https://github.com/robsousax/sistema-itr)")

st.caption(f"Dados: {d.pasta.relative_to(RAIZ).as_posix()}/ · Sistema ITR, projeto de portfólio em "
           "contabilidade societária e controladoria")
