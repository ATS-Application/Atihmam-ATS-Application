"""
reprocess_pending_cvs.py
========================
Script de relance manuelle du traitement IA pour tous les CVs en attente.

Etapes :
  1. Remet a 'queued' les CVs bloques en statut 'processing' (processus interrompu)
  2. Affiche un inventaire des CVs par statut
  3. Lance le pipeline IA sur tous les candidats 'queued'

Usage :
  python reprocess_pending_cvs.py [--batch-size N] [--dry-run] [--reset-failed]
"""

from __future__ import annotations

import argparse
import sys
import os

# Ajoute le repertoire backend au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Charge le .env avant tout import applicatif
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def parse_args():
    parser = argparse.ArgumentParser(description="Relancer le traitement IA des CVs en attente")
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="Nombre de CVs a traiter par lot (defaut: 50)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Affiche uniquement l'inventaire sans lancer le traitement"
    )
    parser.add_argument(
        "--reset-failed", action="store_true",
        help="Remet aussi les CVs 'failed' a 'queued' pour les retraiter"
    )
    return parser.parse_args()


def get_inventory(supabase) -> dict:
    """Recupere le nombre de candidats par statut de traitement."""
    result = {}
    for status in ["queued", "pending", "processing", "completed", "failed", "failed_quota", "retry_scheduled"]:
        resp = (
            supabase.table("candidates")
            .select("id", count="exact")
            .eq("processing_status", status)
            .execute()
        )
        result[status] = resp.count or 0
    return result


def reset_stuck_processing(supabase, dry_run: bool = False) -> int:
    """
    Remet a 'queued' les CVs bloques en statut 'processing'.
    Ces CVs sont ceux dont le traitement a ete interrompu (crash, timeout, etc.)
    """
    resp = (
        supabase.table("candidates")
        .select("id, updated_at")
        .eq("processing_status", "processing")
        .execute()
    )
    stuck = resp.data or []
    count = len(stuck)

    if count == 0:
        print("  [OK] Aucun CV bloque en statut 'processing'.")
        return 0

    print(f"  [!] {count} CV(s) bloques en statut 'processing' detectes.")

    if dry_run:
        print("  [DRY RUN] Remise a 'queued' ignoree.")
        return count

    ids = [c["id"] for c in stuck]
    for i in range(0, len(ids), 50):
        batch_ids = ids[i:i+50]
        supabase.table("candidates").update({
            "processing_status": "queued",
            "processing_error": None,
        }).in_("id", batch_ids).execute()

    print(f"  [OK] {count} CV(s) remis a 'queued' pour retraitement.")
    return count


def reset_failed_candidates(supabase, dry_run: bool = False) -> int:
    """Remet les CVs 'failed' et 'failed_quota' a 'queued' pour les retraiter."""
    resp = (
        supabase.table("candidates")
        .select("id")
        .in_("processing_status", ["failed", "failed_quota"])
        .execute()
    )
    failed = resp.data or []
    count = len(failed)

    if count == 0:
        print("  [OK] Aucun CV en statut 'failed' ou 'failed_quota'.")
        return 0

    print(f"  [!] {count} CV(s) en statut 'failed'/'failed_quota' detectes.")

    if dry_run:
        print("  [DRY RUN] Remise a 'queued' ignoree.")
        return count

    ids = [c["id"] for c in failed]
    for i in range(0, len(ids), 50):
        batch_ids = ids[i:i+50]
        supabase.table("candidates").update({
            "processing_status": "queued",
            "processing_error": None,
        }).in_("id", batch_ids).execute()

    print(f"  [OK] {count} CV(s) remis a 'queued' pour retraitement.")
    return count


def main():
    args = parse_args()

    print()
    print("=" * 60)
    print("  RETRAITEMENT DES CVS EN ATTENTE --- ATS Atihmam")
    print("=" * 60)

    # Import des modules applicatifs (apres load_dotenv)
    from app.db.supabase_client import get_supabase_admin
    from app.tasks.ai_processing import process_queued_candidates

    supabase = get_supabase_admin()

    # -- Etape 1 : Inventaire initial ----------------------------------------
    print("\n[INVENTAIRE INITIAL]")
    inventory = get_inventory(supabase)
    total_pending = (
        inventory.get("queued", 0)
        + inventory.get("pending", 0)
        + inventory.get("processing", 0)
        + inventory.get("failed_quota", 0)
        + inventory.get("retry_scheduled", 0)
    )
    
    def get_label(status_name):
        return {
            "queued": "En file (queued)",
            "pending": "En file (pending)",
            "processing": "En cours",
            "completed": "Terminés",
            "failed": "Échecs",
            "failed_quota": "Quota atteint",
            "retry_scheduled": "Réessai planifié"
        }.get(status_name, status_name)

    for status_name, count in inventory.items():
        print(f"   {status_name:18s} ({get_label(status_name):18s}) : {count:4d} candidat(s)")
    print(f"\n   >> Total non traités : {total_pending} (queued + pending + processing + failed_quota + retry_scheduled)")

    if args.dry_run:
        print("\n[MODE DRY RUN --- aucune action ne sera effectuee]\n")

    # -- Etape 2 : Remise a queued des CVs bloques ---------------------------
    print("\n[REMISE EN FILE DES CVS BLOQUES EN 'processing']")
    reset_count = reset_stuck_processing(supabase, dry_run=args.dry_run)

    # -- Etape 3 : Optionnel --- remise a queued des CVs failed ---------------
    if args.reset_failed:
        print("\n[REMISE EN FILE DES CVS 'failed' & 'failed_quota']")
        reset_count += reset_failed_candidates(supabase, dry_run=args.dry_run)

    # -- Etape 4 : Inventaire apres remise ------------------------------------
    if not args.dry_run and reset_count > 0:
        print("\n[INVENTAIRE APRES REMISE]")
        inventory = get_inventory(supabase)
        for status_name, count in inventory.items():
            print(f"   {status_name:18s} ({get_label(status_name):18s}) : {count:4d} candidat(s)")

    inv = get_inventory(supabase)
    total_to_process = inv.get("queued", 0) + inv.get("pending", 0) + inv.get("retry_scheduled", 0)

    if total_to_process == 0:
        print("\n[OK] Aucun CV en attente de traitement. Tout est deja traite !")
        return

    if args.dry_run:
        print(f"\n[DRY RUN] {total_to_process} CV(s) seraient traites avec batch_size={args.batch_size}.")
        print("Relancez sans --dry-run pour effectuer le traitement.\n")
        return

    # -- Etape 5 : Lancement du traitement IA ---------------------------------
    print(f"\n[LANCEMENT DU TRAITEMENT IA]")
    print(f"   Batch size  : {args.batch_size}")
    print(f"   CVs en file : {total_to_process}")
    print()

    # Traitement par lots jusqu'a epuisement de la file
    total_processed = 0
    total_failed    = 0
    batch_num       = 0

    while True:
        inv = get_inventory(supabase)
        remaining = inv.get("queued", 0) + inv.get("pending", 0) + inv.get("retry_scheduled", 0)
        if remaining == 0:
            break

        batch_num += 1
        batch_to_do = min(args.batch_size, remaining)
        print(f"  -- Lot #{batch_num} : traitement de {batch_to_do} CV(s) ({remaining} restants) --")

        result = process_queued_candidates(batch_size=args.batch_size)
        processed = result.get("processed", 0)
        failed    = result.get("failed", 0)

        total_processed += processed
        total_failed    += failed

        print(f"     Reussis : {processed}")
        print(f"     Echoues : {failed}")
        print()

        # Securite anti-boucle infinie si rien n'a avance
        if processed == 0 and failed == 0:
            print("  [!] Aucun CV traite dans ce lot --- arret de la boucle.")
            break

    # -- Rapport final --------------------------------------------------------
    print("=" * 60)
    print("  RAPPORT FINAL")
    print("=" * 60)
    print(f"  Total reussis  : {total_processed}")
    print(f"  Total echoues  : {total_failed}")
    print(f"  Lots effectues : {batch_num}")

    print("\n[INVENTAIRE FINAL]")
    final_inv = get_inventory(supabase)
    for status_name, count in final_inv.items():
        print(f"   {status_name:18s} ({get_label(status_name):18s}) : {count:4d} candidat(s)")
    print()


if __name__ == "__main__":
    main()
