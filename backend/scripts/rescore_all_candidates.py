import os
import sys
import logging

# Ajout du répertoire parent au path pour importer les modules de l'app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.supabase_client import get_supabase_admin
from app.tasks.cv_processing import build_candidate_payload, compute_best_job_match, fetch_active_jobs, _quality_fallback
from app.services.scoring_service import compute_candidate_score, enrich_cv_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rescore_script")

def rescore_all():
    """
    Force le re-scoring massif de tous les candidats.
    Cette opération recalcule :
    1. Le domaine du candidat et du poste (nouvelles règles)
    2. Le score basé uniquement sur le référentiel métier (plus d'interprétation IA)
    """
    supabase = get_supabase_admin()
    
    # 1. Récupération de tous les candidats
    logger.info("Récupération des candidats...")
    candidates = supabase.table("candidates").select("*").execute().data
    
    # 2. Récupération des jobs actifs pour le matching
    logger.info("Récupération des postes actifs...")
    jobs = fetch_active_jobs(supabase)
    
    logger.info(f"Traitement de {len(candidates)} candidats...")

    success_count = 0
    error_count = 0

    for cand in candidates:
        try:
            cand_id = cand['id']
            name = cand.get('full_name', 'Inconnu')
            
            raw_text = cand.get("cv_raw_text")
            if not raw_text:
                logger.warning(f"Pas de texte brut pour {name} ({cand_id}), passage au suivant.")
                continue
                
            ai_info = cand.get("ai_extracted_data", {})
            # On injecte le texte brut pour que le scoring utilise le référentiel complet
            enriched_cv = enrich_cv_data(ai_info, raw_text)
            
            # 3. Résolution du scoring (Match Job ou Fallback Qualité)
            score_result = None
            job_id = cand.get("job_id")
            
            # Si le candidat était déjà lié à un job spécifique
            if job_id:
                job_res = supabase.table("jobs").select("*").eq("id", job_id).single().execute()
                if job_res.data:
                    job = job_res.data
                    score_result = compute_candidate_score(
                        cv_data=enriched_cv,
                        job_title=job.get("title", ""),
                        job_requirements=job.get("requirements", ""),
                    )
            
            # Si pas de job spécifique ou échec, on cherche le meilleur match parmi les actifs
            if not score_result and jobs:
                score_result, job_id = compute_best_job_match(supabase, enriched_cv, jobs)
                
            # Fallback final si aucun job ne correspond
            if not score_result:
                score_result = _quality_fallback(enriched_cv)
                
            # 4. Construction du payload et mise à jour
            payload = build_candidate_payload(
                raw_text=raw_text,
                cv_info=ai_info,
                enriched_cv=enriched_cv,
                score_result=score_result,
                job_id=job_id
            )
            
            supabase.table("candidates").update(payload).eq("id", cand_id).execute()
            logger.info(f"✓ {name} : {score_result.get('domain')} - Score: {score_result.get('score')}/100")
            success_count += 1
            
        except Exception as e:
            logger.error(f"Erreur lors du re-scoring de {cand.get('id')}: {e}")
            error_count += 1

    logger.info(f"Terminé. Succès: {success_count}, Échecs: {error_count}")

if __name__ == "__main__":
    rescore_all()