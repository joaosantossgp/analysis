"""Static metadata catalog and seeding routines for the ANEEL electricity distribution analytics domain."""
from __future__ import annotations

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── 1. Economic Groups ────────────────────────────────────────────────────────
ECONOMIC_GROUPS = [
    ("neoenergia", "Neoenergia"),
    ("cpfl", "CPFL Energia"),
    ("energisa", "Energisa"),
    ("equatorial", "Equatorial Energia"),
    ("cemig", "Cemig"),
    ("copel", "Copel"),
    ("light", "Light"),
    ("enel", "Enel Brasil"),
    ("state_rs", "Estado do Rio Grande do Sul"),
    ("state_df", "Governo do Distrito Federal"),
]

# ── 2. Listed Companies ────────────────────────────────────────────────────────
# Matches cd_cvm codes and tickers from cvm_financials.db exactly
LISTED_COMPANIES = [
    (15539, "NEOENERGIA S.A.", "NEOE3.SA", "01541288000130"),
    (18660, "CPFL ENERGIA S.A.", "CPFE3.SA", "02429056000115"),
    (15253, "ENERGISA S.A.", "ENGI11.SA", "00826596000195"),
    (20010, "EQUATORIAL ENERGIA S.A.", "EQTL3.SA", "03220556000115"),
    (2453, "COMPANHIA ENERGETICA DE MINAS GERAIS - CEMIG", "CMIG4.SA", "17155730000164"),
    (14311, "COMPANHIA PARANAENSE DE ENERGIA - COPEL", "CPLE6.SA", "76483817000120"),
    (19879, "LIGHT S.A.", "LIGT3.SA", "03378521000190"),
    (14451, "CEB - COMPANHIA ENERGETICA DE BRASILIA", "CEBR3.SA", "000722669000192"),
]

# ── 3. Distributors ───────────────────────────────────────────────────────────
# Major distributors under our target economic groups and listed companies
DISTRIBUTORS = [
    # Neoenergia Group
    ("coelba", "Neoenergia Coelba", "COELBA", "15139629000194", "48", "concession", "BA"),
    ("celpe", "Neoenergia Pernambuco (Celpe)", "CELPE", "10835932000108", "81", "concession", "PE"),
    ("cosern", "Neoenergia Cosern", "COSERN", "08324196000181", "82", "concession", "RN"),
    ("elektro", "Neoenergia Elektro", "ELEKTRO", "02328280000197", "409", "concession", "SP"),
    ("neoenergia_brasilia", "Neoenergia Brasília (CEB-D)", "NEOENERGIA BRASÍLIA", "07522669000192", "61", "concession", "DF"),

    # CPFL Energia Group
    ("cpfl_paulista", "CPFL Paulista", "CPFL PAULISTA", "33050196000188", "25", "concession", "SP"),
    ("cpfl_piratininga", "CPFL Piratininga", "CPFL PIRATININGA", "04172213000138", "259", "concession", "SP"),
    ("cpfl_santa_cruz", "CPFL Santa Cruz", "CPFL SANTA CRUZ", "53859112000169", "272", "concession", "SP"),
    ("rge", "RGE", "RGE", "02016440000162", "329", "concession", "RS"),

    # Energisa Group
    ("energisa_acre", "Energisa Acre (EAC)", "EAC", "04065033000170", "273", "concession", "AC"),
    ("energisa_rondonia", "Energisa Rondônia (ERO)", "ERO", "05914650000166", "274", "concession", "RO"),
    ("energisa_sergipe", "Energisa Sergipe", "ENERGISA SE", "13018789000156", "55", "concession", "SE"),
    ("energisa_paraiba", "Energisa Paraíba", "ENERGISA PB", "09095183000140", "56", "concession", "PB"),
    ("energisa_borborema", "Energisa Borborema", "ENERGISA BORBOREMA", "08826596000195", "57", "concession", "PB"),
    ("energisa_minas_rio", "Energisa Minas Rio", "ENERGISA MINAS RIO", "17189658000162", "58", "concession", "MG"),
    ("energisa_nova_friburgo", "Energisa Nova Friburgo", "ENERGISA NF", "30297098000170", "59", "concession", "RJ"),
    ("energisa_mato_grosso", "Energisa Mato Grosso", "ENERGISA MT", "03467321000199", "64", "concession", "MT"),
    ("energisa_ms", "Energisa Mato Grosso do Sul", "ENERGISA MS", "15413826000150", "65", "concession", "MS"),
    ("energisa_tocantins", "Energisa Tocantins", "ENERGISA TO", "25086034000171", "270", "concession", "TO"),
    ("energisa_sul_sudeste", "Energisa Sul-Sudeste", "ENERGISA SUL-SUDESTE", "61810158000169", "67", "concession", "SP"),

    # Equatorial Group
    ("equatorial_ma", "Equatorial Maranhão (Cemar)", "EQUATORIAL MA", "06272793000184", "63", "concession", "MA"),
    ("equatorial_pa", "Equatorial Pará (Celpa)", "EQUATORIAL PA", "04895728000180", "62", "concession", "PA"),
    ("equatorial_al", "Equatorial Alagoas (Ceal)", "EQUATORIAL AL", "12272084000100", "87", "concession", "AL"),
    ("equatorial_pi", "Equatorial Piauí (Cepisa)", "EQUATORIAL PI", "06840748000189", "86", "concession", "PI"),
    ("equatorial_rs", "Equatorial Rio Grande do Sul (CEEE-D)", "EQUATORIAL RS", "92715812000131", "113", "concession", "RS"),
    ("equatorial_go", "Equatorial Goiás (Celg-D)", "EQUATORIAL GO", "01541288000130", "674", "concession", "GO"),

    # Other Majors
    ("cemig_d", "Cemig Distribuição", "CEMIG D", "06981180000116", "60", "concession", "MG"),
    ("copel_d", "Copel Distribuição", "COPEL D", "04368865000166", "78", "concession", "PR"),
    ("light_servicos", "Light Serviços de Eletricidade", "LIGHT", "03378521000190", "36", "concession", "RJ"),
    ("enel_rj", "Enel Rio", "ENEL RJ", "33050071000158", "35", "concession", "RJ"),
    ("enel_ce", "Enel Ceará", "ENEL CE", "07047251000170", "83", "concession", "CE"),
    ("enel_sp", "Enel São Paulo", "ENEL SP", "61695227000193", "298", "concession", "SP"),
]

# ── 4. Aliases (Maps various source keys and names) ──────────────────────────
# Formats: (alias_id, distributor_id, source, source_cnpj, source_name)
ALIASES = [
    # Coelba
    ("coelba_cnpj", "coelba", "ANEEL", "15139629000194", "COELBA"),
    ("coelba_name", "coelba", "ANEEL", None, "COMPANHIA DE ELETRICIDADE DO ESTADO DA BAHIA - COELBA"),
    # Celpe
    ("celpe_cnpj", "celpe", "ANEEL", "10835932000108", "CELPE"),
    # Cosern
    ("cosern_cnpj", "cosern", "ANEEL", "08324196000181", "COSERN"),
    # Elektro
    ("elektro_cnpj", "elektro", "ANEEL", "02328280000197", "ELEKTRO"),
    # CEB-D / Neoenergia Brasília
    ("ceb_d_cnpj", "neoenergia_brasilia", "ANEEL", "07522669000192", "CEB DIS"),
    ("ceb_d_alias1", "neoenergia_brasilia", "ANEEL", None, "COMPANHIA ENERGÉTICA DE BRASÍLIA - CEB"),
    ("ceb_d_alias2", "neoenergia_brasilia", "ANEEL", None, "NEOENERGIA DISTRIBUIÇÃO BRASÍLIA S.A."),
    # CPFL Paulista
    ("cpfl_paulista_cnpj", "cpfl_paulista", "ANEEL", "33050196000188", "CPFL PAULISTA"),
    # CPFL Piratininga
    ("cpfl_pira_cnpj", "cpfl_piratininga", "ANEEL", "04172213000138", "CPFL PIRATININGA"),
    # CPFL Santa Cruz
    ("cpfl_st_cnpj", "cpfl_santa_cruz", "ANEEL", "53859112000169", "CPFL SANTA CRUZ"),
    ("cpfl_jaguari", "cpfl_santa_cruz", "ANEEL", None, "CPFL JAGUARI"),
    # RGE
    ("rge_cnpj", "rge", "ANEEL", "02016440000162", "RGE"),
    # EAC
    ("energisa_acre_cnpj", "energisa_acre", "ANEEL", "04065033000170", "EAC"),
    # ERO
    ("energisa_ro_cnpj", "energisa_rondonia", "ANEEL", "05914650000166", "ERO"),
    # Cemar
    ("equatorial_ma_cnpj", "equatorial_ma", "ANEEL", "06272793000184", "EQUATORIAL MA"),
    # Celpa
    ("equatorial_pa_cnpj", "equatorial_pa", "ANEEL", "04895728000180", "EQUATORIAL PA"),
    # CEEE-D
    ("equatorial_rs_cnpj", "equatorial_rs", "ANEEL", "92715812000131", "EQUATORIAL RS"),
    ("ceee_d_alias1", "equatorial_rs", "ANEEL", None, "COMPANHIA ESTADUAL DE DISTRIBUIÇÃO DE ENERGIA ELÉTRICA - CEEE-D"),
    # Celg-D
    ("equatorial_go_cnpj", "equatorial_go", "ANEEL", "01541288000130", "EQUATORIAL GO"),
    # Cemig-D
    ("cemig_d_cnpj", "cemig_d", "ANEEL", "06981180000116", "CEMIG D"),
    # Copel-D
    ("copel_d_cnpj", "copel_d", "ANEEL", "04368865000166", "COPEL D"),
    # Light
    ("light_serv_cnpj", "light_servicos", "ANEEL", "03378521000190", "LIGHT"),
]

# ── 5. Ownership History (Curated mapping of control transitions) ────────────
# Formats: (ownership_id, distributor_id, economic_group_id, cd_cvm, valid_from, valid_to, control_status, operational_consolidation_flag)
OWNERSHIP_HISTORY = [
    # Neoenergia Group Stable Controls
    ("coelba_neo", "coelba", "neoenergia", 15539, "2000-01-01", "2099-12-31", "controlled", 1),
    ("celpe_neo", "celpe", "neoenergia", 15539, "2000-01-01", "2099-12-31", "controlled", 1),
    ("cosern_neo", "cosern", "neoenergia", 15539, "2000-01-01", "2099-12-31", "controlled", 1),
    ("elektro_neo", "elektro", "neoenergia", 15539, "2017-08-24", "2099-12-31", "controlled", 1),

    # CEB-D Transition: Owned by CEB (State Company) -> sold to Neoenergia in Mar 2021
    ("ceb_d_state", "neoenergia_brasilia", "state_df", 14451, "2000-01-01", "2021-03-01", "controlled", 1),
    ("ceb_d_neo", "neoenergia_brasilia", "neoenergia", 15539, "2021-03-02", "2099-12-31", "controlled", 1),

    # CPFL Energia Group Controls
    ("cpfl_paulista_cpfl", "cpfl_paulista", "cpfl", 18660, "2000-01-01", "2099-12-31", "controlled", 1),
    ("cpfl_pira_cpfl", "cpfl_piratininga", "cpfl", 18660, "2000-01-01", "2099-12-31", "controlled", 1),
    ("cpfl_st_cpfl", "cpfl_santa_cruz", "cpfl", 18660, "2000-01-01", "2099-12-31", "controlled", 1),
    ("rge_cpfl", "rge", "cpfl", 18660, "2000-01-01", "2099-12-31", "controlled", 1),

    # Energisa Group Controls
    ("energisa_acre_engi", "energisa_acre", "energisa", 15253, "2018-08-30", "2099-12-31", "controlled", 1),
    ("energisa_ro_engi", "energisa_rondonia", "energisa", 15253, "2018-08-30", "2099-12-31", "controlled", 1),
    ("energisa_se_engi", "energisa_sergipe", "energisa", 15253, "2000-01-01", "2099-12-31", "controlled", 1),
    ("energisa_pb_engi", "energisa_paraiba", "energisa", 15253, "2000-01-01", "2099-12-31", "controlled", 1),
    ("energisa_borb_engi", "energisa_borborema", "energisa", 15253, "2000-01-01", "2099-12-31", "controlled", 1),
    ("energisa_mr_engi", "energisa_minas_rio", "energisa", 15253, "2000-01-01", "2099-12-31", "controlled", 1),
    ("energisa_nf_engi", "energisa_nova_friburgo", "energisa", 15253, "2000-01-01", "2099-12-31", "controlled", 1),
    ("energisa_mt_engi", "energisa_mato_grosso", "energisa", 15253, "2014-04-11", "2099-12-31", "controlled", 1),
    ("energisa_ms_engi", "energisa_ms", "energisa", 15253, "2014-04-11", "2099-12-31", "controlled", 1),
    ("energisa_to_engi", "energisa_tocantins", "energisa", 15253, "2014-04-11", "2099-12-31", "controlled", 1),
    ("energisa_ss_engi", "energisa_sul_sudeste", "energisa", 15253, "2014-04-11", "2099-12-31", "controlled", 1),

    # Equatorial Group Controls
    ("equatorial_ma_eq", "equatorial_ma", "equatorial", 20010, "2004-06-15", "2099-12-31", "controlled", 1),
    ("equatorial_pa_eq", "equatorial_pa", "equatorial", 20010, "2012-11-01", "2099-12-31", "controlled", 1),
    ("equatorial_al_eq", "equatorial_al", "equatorial", 20010, "2019-03-18", "2099-12-31", "controlled", 1),
    ("equatorial_pi_eq", "equatorial_pi", "equatorial", 20010, "2018-10-17", "2099-12-31", "controlled", 1),

    # CEEE-D Transition: Owned by RS State -> sold to Equatorial in Jul 2021
    ("ceee_d_state", "equatorial_rs", "state_rs", None, "2000-01-01", "2021-07-28", "controlled", 1),
    ("ceee_d_eq", "equatorial_rs", "equatorial", 20010, "2021-07-29", "2099-12-31", "controlled", 1),

    # Celg-D Transition: Owned by Enel -> sold to Equatorial in Jan 2023
    ("celg_d_enel", "equatorial_go", "enel", None, "2016-11-30", "2023-01-02", "controlled", 1),
    ("celg_d_eq", "equatorial_go", "equatorial", 20010, "2023-01-03", "2099-12-31", "controlled", 1),

    # Other Majors
    ("cemig_d_cem", "cemig_d", "cemig", 2453, "2000-01-01", "2099-12-31", "controlled", 1),
    ("copel_d_cop", "copel_d", "copel", 14311, "2000-01-01", "2099-12-31", "controlled", 1),
    ("light_li", "light_servicos", "light", 19879, "2000-01-01", "2099-12-31", "controlled", 1),
]

# ── 6. Delinquency Coded Indicators ───────────────────────────────────────────
_DELINQUENCY_CLASSES = {
    "ICProp": "Consumo Proprio",
    "ICom": "Comercial",
    "IIPub": "Iluminacao Publica",
    "IInd": "Industrial",
    "IPPub": "Poder Publico",
    "IResBR": "Residencial Baixa Renda",
    "IResTot": "Residencial Total",
    "IRestot": "Residencial Total",
    "IRur": "Rural",
    "ISerPub": "Servico Publico",
    "ITot": "Todos os consumidores",
}

_DELINQUENCY_AGE_SUFFIXES = ("1", "3", "6", "12", "18", "21", "24")


def _delinquency_indicator_rows() -> list[tuple[str, str, str, str, str, str, int]]:
    """Build the official Inadimplencia code domain observed in ANEEL's resource.

    The official dominio-indicadores.csv names the same family/suffix pattern:
    age suffixes are percentages of billed revenue from the referenced prior
    month not received in the reference month; Crt suffixes are suspension
    counts for delinquency in the reference month.
    """
    rows: list[tuple[str, str, str, str, str, str, int]] = []
    for prefix, class_name in _DELINQUENCY_CLASSES.items():
        if prefix == "IResTot":
            age_suffixes = ("1",)
        elif prefix == "IRestot":
            age_suffixes = ("3", "6", "12", "18", "21", "24")
        else:
            age_suffixes = _DELINQUENCY_AGE_SUFFIXES

        for suffix in age_suffixes:
                code = f"{prefix}{suffix}"
                rows.append((
                    code,
                    code,
                    f"Perc. da rec. fat. {suffix} mes ant. nao receb. no mes de ref. classe {class_name}",
                    "percent",
                    "total_delinquency" if prefix == "ITot" else "aging_bucket",
                    "lead_kpi" if prefix == "ITot" else "supporting_fact",
                    1 if prefix == "ITot" else 0,
                ))
        if prefix != "IRestot":
            crt_code = f"{prefix}Crt"
            rows.append((
                crt_code,
                crt_code,
                f"Quant. de unid. da classe {class_name} susp. inadimplencia no mes de ref.",
                "consumer_units",
                "suspension_metric",
                "supporting_fact",
                0,
            ))
    return sorted(rows, key=lambda row: row[0])


DELINQUENCY_INDICATORS = _delinquency_indicator_rows()

# ── 7. ANEEL Open Data Resource Catalog ───────────────────────────────────────
# Dict structure containing dataset URLs, formats and identifiers
ANEEL_RESOURCES = {
    "samp_balanco": {
        "resource_id": "cffe3c15-9d3e-4187-ae63-e097cf88c0af",
        "url": "https://dadosabertos.aneel.gov.br/dataset/3193ebab-81b3-406e-be0e-f968a4a21689/resource/cffe3c15-9d3e-4187-ae63-e097cf88c0af/download/samp-balanco.parquet",
        "format": "parquet",
        "file_name": "samp-balanco.parquet"
    },
    "samp_mercado": {
        2016: {
            "resource_id": "625190de-b2d8-4298-9a16-8614c81ebdad",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/625190de-b2d8-4298-9a16-8614c81ebdad/download/samp-2016.parquet",
            "format": "parquet",
            "file_name": "samp-2016.parquet"
        },
        2017: {
            "resource_id": "e60f6ae3-c69e-41c8-bdc7-16b61ac5e0d0",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/e60f6ae3-c69e-41c8-bdc7-16b61ac5e0d0/download/samp-2017.parquet",
            "format": "parquet",
            "file_name": "samp-2017.parquet"
        },
        2018: {
            "resource_id": "99275309-636d-477b-aa2c-cda6b0c0550e",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/99275309-636d-477b-aa2c-cda6b0c0550e/download/samp-2018.parquet",
            "format": "parquet",
            "file_name": "samp-2018.parquet"
        },
        2019: {
            "resource_id": "02cf17ae-36e5-4ffb-950d-5525ac9da34d",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/02cf17ae-36e5-4ffb-950d-5525ac9da34d/download/samp-2019.parquet",
            "format": "parquet",
            "file_name": "samp-2019.parquet"
        },
        2020: {
            "resource_id": "89a21870-8ff4-4b86-a0be-b1ba64a9d6f2",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/89a21870-8ff4-4b86-a0be-b1ba64a9d6f2/download/samp-2020.parquet",
            "format": "parquet",
            "file_name": "samp-2020.parquet"
        },
        2021: {
            "resource_id": "541d5ce5-d6e6-4632-b32f-7a045e1e10fe",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/541d5ce5-d6e6-4632-b32f-7a045e1e10fe/download/samp-2021.parquet",
            "format": "parquet",
            "file_name": "samp-2021.parquet"
        },
        2022: {
            "resource_id": "99294049-1c6b-4991-9f59-ae0872bbbae2",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/99294049-1c6b-4991-9f59-ae0872bbbae2/download/samp-2022.parquet",
            "format": "parquet",
            "file_name": "samp-2022.parquet"
        },
        2023: {
            "resource_id": "04c9bb85-6074-4fd1-a697-ecde329309dc",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/04c9bb85-6074-4fd1-a697-ecde329309dc/download/samp-2023.parquet",
            "format": "parquet",
            "file_name": "samp-2023.parquet"
        },
        2024: {
            "resource_id": "018d9180-eced-441f-8ede-d205b50421e9",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/018d9180-eced-441f-8ede-d205b50421e9/download/samp-2024.parquet",
            "format": "parquet",
            "file_name": "samp-2024.parquet"
        },
        2025: {
            "resource_id": "a757e805-fe7b-4764-bb49-19caef3e5dfe",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/a757e805-fe7b-4764-bb49-19caef3e5dfe/download/samp-2025.parquet",
            "format": "parquet",
            "file_name": "samp-2025.parquet"
        },
        2026: {
            "resource_id": "56f1c242-5017-4cef-a365-0a96fffb0f2b",
            "url": "https://dadosabertos.aneel.gov.br/dataset/3e153db4-a503-4093-88be-75d31b002dcf/resource/56f1c242-5017-4cef-a365-0a96fffb0f2b/download/samp-2026.csv",
            "format": "csv",
            "file_name": "samp-2026.csv"
        }
    },
    "continuity_actuals": {
        "10_19": {
            "resource_id": "1706a88f-ecd6-4de9-99ee-ec240c317378",
            "url": "https://dadosabertos.aneel.gov.br/dataset/d5f0712e-62f6-4736-8dff-9991f10758a7/resource/1706a88f-ecd6-4de9-99ee-ec240c317378/download/indicadores-continuidade-coletivos-2010-2019.parquet",
            "format": "parquet",
            "file_name": "indicadores-continuidade-coletivos-2010-2019.parquet"
        },
        "20_29": {
            "resource_id": "4493985c-baea-429c-9df5-3030422c71d7",
            "url": "https://dadosabertos.aneel.gov.br/dataset/d5f0712e-62f6-4736-8dff-9991f10758a7/resource/4493985c-baea-429c-9df5-3030422c71d7/download/indicadores-continuidade-coletivos-2020-2029.csv",
            "format": "csv",
            "file_name": "indicadores-continuidade-coletivos-2020-2029.csv"
        }
    },
    "continuity_limits": {
        "resource_id": "fd69e1dd-fd66-4269-b60c-cc0b7eb221b4",
        "url": "https://dadosabertos.aneel.gov.br/dataset/d5f0712e-62f6-4736-8dff-9991f10758a7/resource/fd69e1dd-fd66-4269-b60c-cc0b7eb221b4/download/indicadores-continuidade-coletivos-limite.csv",
        "format": "csv",
        "file_name": "indicadores-continuidade-coletivos-limite.csv"
    },
    "continuity_compensation": {
        "resource_id": "8046471d-a6b1-4c6b-b770-c4ea9e4c88c0",
        "url": "https://dadosabertos.aneel.gov.br/dataset/d5f0712e-62f6-4736-8dff-9991f10758a7/resource/8046471d-a6b1-4c6b-b770-c4ea9e4c88c0/download/indicadores-continuidade-coletivos-compensacao-2010-2019.parquet",
        "format": "parquet",
        "file_name": "indicadores-continuidade-coletivos-compensacao-2010-2019.parquet"
    },
    "tariffs": {
        "resource_id": "fcf2906c-7c32-4b9b-a637-054e7a5234f4",
        "url": "https://dadosabertos.aneel.gov.br/dataset/5a583f3e-1646-4f67-bf0f-69db4203e89e/resource/fcf2906c-7c32-4b9b-a637-054e7a5234f4/download/tarifas-homologadas-distribuidoras-energia-eletrica.csv",
        "format": "csv",
        "file_name": "tarifas-homologadas-distribuidoras-energia-eletrica.csv"
    },
    "delinquency": {
        "resource_id": "0bb73b5d-b2e1-417d-9873-6de6b2d397d1",
        "url": "https://dadosabertos.aneel.gov.br/dataset/af2cc4e5-5a31-4b39-98d5-d759abaf1b9e/resource/0bb73b5d-b2e1-417d-9873-6de6b2d397d1/download/inadimplencia.csv",
        "format": "csv",
        "file_name": "inadimplencia.csv"
    },
    "mmgd_projects": {
        "resource_id": "cd29f6eb-e08d-4db7-b6fb-ed6e3b682d27",
        "url": "https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2/resource/cd29f6eb-e08d-4db7-b6fb-ed6e3b682d27/download/empreendimento-geracao-distribuida.parquet",
        "format": "parquet",
        "file_name": "empreendimento-geracao-distribuida.parquet"
    }
}


def seed_distribution_static_data(conn) -> None:
    """Idempotently seed static master data for distributors, groups, aliases, and indicators."""
    logger.info("Seeding distribution master dimensions and static metadata...")

    # Seed Economic Groups
    conn.execute(text("""
        INSERT OR REPLACE INTO distribution_economic_groups (economic_group_id, group_name)
        VALUES (:id, :name)
    """), [{"id": g[0], "name": g[1]} for g in ECONOMIC_GROUPS])

    # Seed Listed Companies
    conn.execute(text("""
        INSERT OR REPLACE INTO distribution_listed_companies (cd_cvm, company_name, ticker_b3, cnpj)
        VALUES (:cd, :name, :ticker, :cnpj)
    """), [{"cd": lc[0], "name": lc[1], "ticker": lc[2], "cnpj": lc[3]} for lc in LISTED_COMPANIES])

    # Seed Distributors
    conn.execute(text("""
        INSERT OR REPLACE INTO distribution_distributors (
            distributor_id, canonical_name, trade_name, normalized_cnpj,
            agent_code, concession_type, primary_uf
        )
        VALUES (:id, :name, :trade, :cnpj, :code, :type, :uf)
    """), [
        {
            "id": d[0],
            "name": d[1],
            "trade": d[2],
            "cnpj": d[3],
            "code": d[4],
            "type": d[5],
            "uf": d[6]
        }
        for d in DISTRIBUTORS
    ])

    # Seed Aliases
    conn.execute(text("""
        INSERT OR REPLACE INTO distribution_distributor_aliases (
            alias_id, distributor_id, source, source_cnpj, source_name
        )
        VALUES (:id, :dist, :src, :cnpj, :name)
    """), [
        {
            "id": a[0],
            "dist": a[1],
            "src": a[2],
            "cnpj": a[3],
            "name": a[4]
        }
        for a in ALIASES
    ])

    # Seed Ownership History
    conn.execute(text("""
        INSERT OR REPLACE INTO distribution_ownership_history (
            ownership_id, distributor_id, economic_group_id, cd_cvm,
            valid_from, valid_to, control_status, operational_consolidation_flag
        )
        VALUES (:id, :dist, :group, :cvm, :from_dt, :to_dt, :status, :flag)
    """), [
        {
            "id": oh[0],
            "dist": oh[1],
            "group": oh[2],
            "cvm": oh[3],
            "from_dt": oh[4],
            "to_dt": oh[5],
            "status": oh[6],
            "flag": oh[7]
        }
        for oh in OWNERSHIP_HISTORY
    ])

    # Seed Delinquency Indicators
    conn.execute(text("""
        INSERT OR REPLACE INTO distribution_delinquency_indicators (
            indicator_code, indicator_name, description, unit,
            analytical_category, publication_status, is_lead_kpi
        )
        VALUES (:code, :name, :desc, :unit, :category, :status, :lead)
    """), [
        {
            "code": di[0],
            "name": di[1],
            "desc": di[2],
            "unit": di[3],
            "category": di[4],
            "status": di[5],
            "lead": di[6],
        }
        for di in DELINQUENCY_INDICATORS
    ])

    logger.info("Successfully seeded all static distribution metadata.")
