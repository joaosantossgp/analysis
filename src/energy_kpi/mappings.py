import re
import logging
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger(__name__)

IGNORE_WORDS = {
    "cia", "cia.", "companhia", "sociedade", "s/a", "s.a.", "ltda", "ltda.",
    "com", "distribuidora", "geracao", "energia", "participacoes", "holding",
    "grupo", "do", "da", "de", "e", "s.a", "eletro", "eletrica", "energetica",
    "energias", "brasileiras", "nacional", "servicos", "saneamento"
}

def clean_cnpj(val: str | None) -> str:
    if not val:
        return ""
    return "".join(c for c in str(val) if c.isdigit())

def extract_cnpj_root(cnpj: str) -> str:
    cleaned = clean_cnpj(cnpj)
    return cleaned[:8] if len(cleaned) >= 8 else ""

def extract_company_token(name: str) -> str | None:
    words = re.findall(r"\b\w+\b", name.lower())
    for w in words:
        if w not in IGNORE_WORDS and len(w) >= 3:
            return w
    return None

def extract_ticker_prefix(ticker: str | None) -> str:
    if not ticker:
        return ""
    # E.g. CPFE3.SA -> cpfe, EQTL3 -> eqtl
    cleaned = ticker.split(".")[0].upper()
    prefix = "".join(c for c in cleaned if c.isalpha())
    return prefix.lower()

def run_automatic_asset_mapping(energy_conn, cvm_conn) -> dict:
    """
    Idempotently runs automatic asset matching.
    Matches ANEEL Distributors and CCEE Plant Parcels to CVM Listed Companies.
    Does NOT overwrite manual mappings (mapping_source = 'manual').
    """
    logger.info("Starting automatic asset mapping routine...")
    t0 = datetime.utcnow().isoformat()
    
    # 1. Load CVM Companies
    companies_query = text("""
        SELECT cd_cvm, company_name, ticker_b3, cnpj, setor_cvm, gics_sector
        FROM companies
        WHERE is_active = 1
    """)
    cvm_companies = cvm_conn.execute(companies_query).fetchall()
    
    # Pre-parse company match keys
    company_list = []
    for c in cvm_companies:
        cd_cvm, name, ticker, cnpj, setor_cvm, gics_sector = c
        cnpj_root = extract_cnpj_root(cnpj) if cnpj else ""
        name_token = extract_company_token(name) if name else None
        ticker_prefix = extract_ticker_prefix(ticker) if ticker else ""
        
        company_list.append({
            "cd_cvm": cd_cvm,
            "name": name,
            "cnpj_root": cnpj_root,
            "name_token": name_token,
            "ticker_prefix": ticker_prefix,
            "raw_cnpj": clean_cnpj(cnpj)
        })
        
    # 2. Load Existing Manual Mappings to avoid overwriting
    existing_manual_query = text("""
        SELECT asset_id, asset_type FROM conglomerate_asset_mappings
        WHERE mapping_source = 'manual'
    """)
    manual_rows = energy_conn.execute(existing_manual_query).fetchall()
    manual_set = {(r[0], r[1]) for r in manual_rows}
    
    matched_count = 0
    skipped_manual_count = 0
    
    # 3. Match Distributors
    dist_query = text("""
        SELECT distributor_id, canonical_name, trade_name, normalized_cnpj FROM distribution_distributors
    """)
    distributors = energy_conn.execute(dist_query).fetchall()
    
    for d in distributors:
        dist_id, name, trade, cnpj = d
        if (dist_id, "distributor") in manual_set:
            skipped_manual_count += 1
            continue
            
        cnpj_root = extract_cnpj_root(cnpj) if cnpj else ""
        search_names = [val.lower() for val in (name, trade, dist_id) if val]
        
        # Try CNPJ root match first
        best_cvm = None
        if cnpj_root:
            for c in company_list:
                if c["cnpj_root"] and c["cnpj_root"] == cnpj_root:
                    best_cvm = c["cd_cvm"]
                    break
                    
        # Try token/prefix matching if no CNPJ match
        if not best_cvm:
            for c in company_list:
                # Direct name token match
                if c["name_token"] and any(c["name_token"] in s for s in search_names):
                    best_cvm = c["cd_cvm"]
                    break
                # Ticker prefix match
                if c["ticker_prefix"] and any(c["ticker_prefix"] in s for s in search_names):
                    best_cvm = c["cd_cvm"]
                    break
                    
        if best_cvm:
            energy_conn.execute(text("""
                INSERT OR REPLACE INTO conglomerate_asset_mappings (asset_id, asset_type, cd_cvm, mapping_source, updated_at)
                VALUES (:asset_id, 'distributor', :cd_cvm, 'auto', :updated_at)
            """), {"asset_id": dist_id, "cd_cvm": best_cvm, "updated_at": t0})
            matched_count += 1

    # 4. Match Plant Parcels (CCEE Generation)
    plant_query = text("""
        SELECT plant_parcel_code, plant_name, agent_name FROM ccee_plant_parcels
    """)
    plants = energy_conn.execute(plant_query).fetchall()
    
    for p in plants:
        code, plant_name, agent_name = p
        if (code, "plant") in manual_set:
            skipped_manual_count += 1
            continue
            
        search_names = [val.lower() for val in (plant_name, agent_name, code) if val]
        
        best_cvm = None
        # Try token/prefix matching
        for c in company_list:
            if c["name_token"] and any(c["name_token"] in s for s in search_names):
                best_cvm = c["cd_cvm"]
                break
            if c["ticker_prefix"] and any(c["ticker_prefix"] in s for s in search_names):
                best_cvm = c["cd_cvm"]
                break
                
        if best_cvm:
            energy_conn.execute(text("""
                INSERT OR REPLACE INTO conglomerate_asset_mappings (asset_id, asset_type, cd_cvm, mapping_source, updated_at)
                VALUES (:asset_id, 'plant', :cd_cvm, 'auto', :updated_at)
            """), {"asset_id": code, "cd_cvm": best_cvm, "updated_at": t0})
            matched_count += 1
            
    logger.info(f"Auto-mapping complete: {matched_count} assets matched, {skipped_manual_count} manual overrides preserved.")
    return {
        "status": "success",
        "matched": matched_count,
        "preserved_manual": skipped_manual_count
    }
