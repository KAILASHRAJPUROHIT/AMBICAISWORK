import os
import sys
import argparse
import json
from datetime import datetime
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.database import SessionLocal
from backend.models import BankDocument, AuditLog
from backend.bank_document_ingestion import classify_document

def run_backfill():
    parser = argparse.ArgumentParser(description="Backfill BankDocument classification and password profiles.")
    parser.add_argument('--apply', action='store_true', help="Apply changes to the database (defaults to dry-run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{datetime.now()}] Starting Bank Document Classification Backfill (Mode: {mode})")
    
    db = SessionLocal()
    try:
        docs = db.query(BankDocument).all()
        print(f"Found {len(docs)} documents to process.")
        
        summary = {
            "processed": 0,
            "updates_detected": 0,
            "applied": 0,
            "skipped": 0,
            "changes": []
        }

        for doc in docs:
            summary["processed"] += 1
            
            # Re-run classification using metadata strictly
            bank, classification, ftype, reason, profile = classify_document(
                doc.sender, 
                doc.subject, 
                doc.original_filename
            )
            
            has_changed = (
                doc.classification != classification or 
                doc.password_profile != profile or
                doc.bank_name != bank
            )
            
            if has_changed:
                summary["updates_detected"] += 1
                change_entry = {
                    "id": doc.id,
                    "filename": doc.original_filename,
                    "old_class": doc.classification,
                    "new_class": classification,
                    "old_profile": doc.password_profile,
                    "new_profile": profile,
                    "reason": reason
                }
                summary["changes"].append(change_entry)
                
                if args.apply:
                    doc.bank_name = bank
                    doc.classification = classification
                    doc.classification_reason = f"Backfill Update: {reason}"
                    doc.password_profile = profile
                    
                    # Create audit log inline
                    audit = AuditLog(
                        entity_type="BankDocument",
                        entity_id=doc.id,
                        action="METADATA_BACKFILL",
                        actor="SYSTEM",
                        metadata_json=json.dumps(change_entry)
                    )
                    db.add(audit)
                    summary["applied"] += 1
            else:
                summary["skipped"] += 1
        
        if args.apply:
            db.commit()
            print("Changes committed to database.")
        else:
            print("DRY-RUN COMPLETE. No changes were made to the database.")
            if summary["updates_detected"] > 0:
                print(f"Run with --apply to commit {summary['updates_detected']} updates.")

        print("\n--- Backfill Summary ---")
        print(f"Processed        : {summary['processed']}")
        print(f"Updates Detected : {summary['updates_detected']}")
        print(f"Updates Applied  : {summary['applied']}")
        print(f"Skipped          : {summary['skipped']}")
        
        if summary["changes"]:
            print("\n--- Detailed Changes ---")
            for c in summary["changes"]:
                print(f"ID {c['id']} [{c['filename']}]:")
                print(f"  {c['old_class']} -> {c['new_class']}")
                print(f"  Profile: {c['old_profile']} -> {c['new_profile']}")
                print(f"  Reason: {c['reason']}")
                
    except Exception as e:
        print(f"ERROR during backfill: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_backfill()
