"""
backfill_incomplete_cvs.py
==========================
Relance l'extraction IA complète pour tous les candidats dont les informations
clés sont manquantes (full_name vide/placeholder, email vide, ou skills vide).

Ce script :
  1. Identifie les candidats incomplets (status=completed mais infos manquantes)
  2. Remet extracted=False + processing_status='queued' pour forcer la ré-extraction IA
  3. Optionnel : lance immédiatement le pipeline IA (--run)

Usage :
  python backfill_incomplete_cvs.py [--dry-run] [--run] [--batch-size N]

Options :
  --dry-run      Affiche les candidats concernés sans rien modifier
  --run          Lance le traitement IA immédiatement après la remise en file
  --batch-size N Nombre de CVs à traiter par lot (défaut: 20)
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_incomplete(row: dict) -> bool:
    """Return True if the candidate is missing at least one key field."""
    name = (row.get("full_name") or "").strip()
    email = (row.get("email") or "").strip()
    skills = row.get("skills") or []

    name_missing = not name or name.lower().endswith(".pdf") or name.lower().endswith(".docx")
    email_missing = not email
    skills_missing = not skills

    return name_missing or email_missing or skills_missing


def fetch_incomplete_candidates(supabase) -> list[dict]:
    """Fetch ALL candidates and filter those with incomplete info."""
    all_rows: list[dict] = []
    page_size = 1000
    offset = 0

    while True:
        resp = (
            supabase.table("candidates")
            .select("id, full_name, email, skills, processing_status, extracted, cv_file_url")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    return [r for r in all_rows if _is_incomplete(r)]


def reset_for_reextraction(supabase, candidate_ids: list[str], dry_run: bool = False) -> int:
    """Reset candidates so they will be fully re-extracted by the AI."""
    if not candidate_ids:
        return 0

    print(f"\n  Remise à 'queued' avec extracted=False pour {len(candidate_ids)} candidat(s)...")

    if dry_run:
        print("  [DRY RUN] Aucune modification effectuée.")
        return len(candidate_ids)

    for i in range(0, len(candidate_ids), 50):
        batch = candidate_ids[i:i + 50]
        supabase.table("candidates").update({
            "processing_status": "queued",
            "extracted": False,
            "processing_error": None,
        }).in_("id", batch).execute()

    print(f"  [OK] {len(candidate_ids)} candidat(s) remis en file pour ré-extraction.")
    return len(candidate_ids)


# ── Main ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill IA pour les candidats avec informations manquantes"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les candidats concernés sans les modifier")
    parser.add_argument("--run", action="store_true",
                        help="Lance le traitement IA immédiatement après la remise en file")
    parser.add_argument("--batch-size", type=int, default=20,
                        help="Nombre de CVs à traiter par lot lors du --run (défaut: 20)")
    return parser.parse_args()


def main():
    args = parse_args()

    from app.db.supabase_client import get_supabase_admin

    supabase = get_supabase_admin()

    print()
    print("=" * 65)
    print("  BACKFILL — CVs AVEC INFORMATIONS MANQUANTES")
    print("=" * 65)

    # ── 1. Audit ──────────────────────────────────────────────────────
    print("\n[AUDIT DES CANDIDATS INCOMPLETS]")
    incomplete = fetch_incomplete_candidates(supabase)

    if not incomplete:
        print("  [OK] Tous les candidats ont des informations complètes. Rien à faire.")
        return

    # Breakdown
    no_name   = [r for r in incomplete if not (r.get("full_name") or "").strip() or
                 (r.get("full_name") or "").lower().endswith((".pdf", ".docx"))]
    no_email  = [r for r in incomplete if not (r.get("email") or "").strip()]
    no_skills = [r for r in incomplete if not r.get("skills")]

    print(f"  Candidats incomplets trouves  : {len(incomplete)}")
    print(f"    -> Sans nom (ou nom=fichier) : {len(no_name)}")
    print(f"    -> Sans email                : {len(no_email)}")
    print(f"    -> Sans competences          : {len(no_skills)}")

    if args.dry_run:
        print("\n[MODE DRY RUN — aucune modification]\n")
        print("Échantillon (5 premiers) :")
        for r in incomplete[:5]:
            print(f"  id={r['id'][:8]}  name={r.get('full_name')!r}  "
                  f"email={r.get('email')!r}  status={r.get('processing_status')}")
        return

    # ── 2. Remise en file ─────────────────────────────────────────────
    candidate_ids = [r["id"] for r in incomplete]
    reset_for_reextraction(supabase, candidate_ids, dry_run=False)

    # ── 3. Optionnel : lancement IA immédiat ──────────────────────────
    if not args.run:
        print(
            f"\n[INFO] {len(candidate_ids)} CVs en file d'attente."
            "\n  Lancez le traitement IA via le dashboard ou avec :"
            "\n    python reprocess_pending_cvs.py"
            "\n  Ou relancez ce script avec --run pour traiter immédiatement."
        )
        return

    from app.tasks.ai_processing import process_queued_candidates

    print(f"\n[LANCEMENT DU TRAITEMENT IA] batch_size={args.batch_size}")
    total_processed = 0
    total_failed = 0
    batch_num = 0

    while True:
        # Check remaining
        resp = (
            supabase.table("candidates")
            .select("id", count="exact")
            .in_("processing_status", ["queued", "pending", "retry_scheduled"])
            .execute()
        )
        remaining = resp.count or 0
        if remaining == 0:
            break

        batch_num += 1
        print(f"\n  -- Lot #{batch_num} ({remaining} candidats restants) --")
        result = process_queued_candidates(batch_size=args.batch_size)
        processed = result.get("processed", 0)
        failed = result.get("failed", 0)
        total_processed += processed
        total_failed += failed
        print(f"     Réussis : {processed} | Échoués : {failed}")

        if processed == 0 and failed == 0:
            print("  [!] Aucune progression — arrêt.")
            break

    # ── 4. Rapport ────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  RAPPORT FINAL")
    print("=" * 65)
    print(f"  Candidats remis en file : {len(candidate_ids)}")
    print(f"  Réussis                 : {total_processed}")
    print(f"  Échoués                 : {total_failed}")
    print(f"  Lots effectués          : {batch_num}")
    print()


if __name__ == "__main__":
    main()
