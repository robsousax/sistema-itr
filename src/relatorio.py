"""
Coleta tudo o que vai para o ITR (Etapa 10), num só lugar, para o Excel e o PDF usarem os
mesmos números.

A coleta começa pela Central de qualidade: se ela bloquear, nada é montado e nenhum arquivo é
gerado (PermissionError com os erros encontrados).
"""
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import yaml

from checar_config import PASTA_CONFIG, carregar
from comentario import Comentario, escrever_comentario
from demonstracoes import montar_bp, montar_dre, periodos_itr
from dfc_dmpl import montar_dfc, montar_dmpl, transacoes_sem_caixa
from dra_dva import montar as montar_dra_dva
from indicadores import TRIMESTRES, reconciliacao_ebitda, serie
from notas import Nota, montar_notas
from qualidade import Execucao, exigir_liberacao


@dataclass
class Relatorio:
    trimestre: str
    empresa: dict
    periodos: dict
    qualidade: Execucao
    bp: pd.DataFrame
    dre: pd.DataFrame
    lpa: dict
    dra: pd.DataFrame
    dfc: pd.DataFrame
    dmpl: dict[str, pd.DataFrame]
    dva: pd.DataFrame
    notas: list[Nota]
    indicadores: pd.DataFrame
    ebitda: pd.DataFrame
    sem_caixa: list[dict]
    comentario: Comentario
    tipo_linha: dict
    gerado_em: str

    @property
    def data_base(self) -> date:
        return self.periodos["bp_atual"].fim

    @property
    def nome_arquivo(self) -> str:
        return f"ITR_{self.empresa['empresa']['nome_curto']}_{self.trimestre}"


def trimestres_ate(trimestre: str) -> list[str]:
    """Trimestres com histórico até o trimestre do ITR (a série começa no 1T25)."""
    return TRIMESTRES[:TRIMESTRES.index(trimestre) + 1]


def coletar(con, trimestre: str = "3T26", cfg: dict | None = None) -> Relatorio:
    cfg = cfg or carregar()
    qualidade = exigir_liberacao(con, trimestre, cfg)  # bloqueia aqui se houver erro
    with open(PASTA_CONFIG / "empresa.yaml", encoding="utf-8") as f:
        empresa = yaml.safe_load(f)
    p = periodos_itr(trimestre)
    dre, lpa = montar_dre(con, trimestre, cfg)
    dra, dva = montar_dra_dva(con, trimestre, cfg)
    trims = trimestres_ate(trimestre)
    linhas = cfg["dim_linha_df"]
    return Relatorio(
        trimestre=trimestre, empresa=empresa, periodos=p, qualidade=qualidade,
        bp=montar_bp(con, trimestre, cfg), dre=dre, lpa=lpa, dra=dra,
        dfc=montar_dfc(con, trimestre, cfg), dmpl=montar_dmpl(con, trimestre, cfg), dva=dva,
        notas=montar_notas(con, trimestre, cfg),
        indicadores=serie(con, cfg, trims), ebitda=reconciliacao_ebitda(con, cfg, trims),
        sem_caixa=transacoes_sem_caixa(con, p["acum_atual"].inicio, p["acum_atual"].fim),
        comentario=escrever_comentario(con, trimestre, cfg),
        tipo_linha=dict(zip(zip(linhas.demonstracao, linhas.codigo), linhas.tipo_linha)),
        gerado_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )
