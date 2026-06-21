#!/usr/bin/env python3
"""
Clean up malformed / duplicated user subjects left behind by the old
registration flow.

Two past bugs polluted the ``subjects`` table:
  1. A raw menu number (e.g. "4") was persisted as ``subject_name`` instead of
     the category name ("Política e economia amazônica").
  2. Subjects were never cleared between registrations / edits, so they
     accumulated and duplicated per user.

This script repairs existing rows:
  1. Maps recognizable menu numbers back to their category name
     (1 -> "Todos temas", 2-6 -> category) so the user's choice is preserved.
  2. Deletes leftover subjects whose name is still numeric or empty and cannot
     be mapped.
  3. Deduplicates subjects per user (case-insensitive), keeping the earliest row.

By default it runs in DRY-RUN mode and only reports what it *would* do; pass
``--apply`` to actually write the changes.

Usage:
    python scripts/cleanup_subjects.py                 # preview only (no writes)
    python scripts/cleanup_subjects.py --apply         # apply the changes
    python scripts/cleanup_subjects.py --apply --delete-numbers
        # delete numeric rows instead of mapping them to category names
"""

import sys
import os
import argparse
import logging

# Allow imports from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from services.chatgpt import SUBJECT_MENU

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Menu option 1 means "all topics"; 2-6 come from the shared SUBJECT_MENU.
NUMBER_TO_NAME = {"1": "Todos temas", **SUBJECT_MENU}


def cleanup_subjects(apply_changes: bool, delete_numbers: bool) -> dict:
    """Repair numeric/empty subject names and drop per-user duplicates.

    Returns a dict of counters describing the actions taken (or, in dry-run,
    the actions that would be taken).
    """
    session = SessionLocal()
    stats = {"scanned": 0, "mapped": 0, "deleted_empty": 0,
             "deleted_numeric": 0, "deleted_duplicate": 0}

    try:
        # Deterministic order: keep the earliest row (smallest id) per user.
        subjects = (
            session.query(models.Subject)
            .order_by(models.Subject.user_id, models.Subject.id)
            .all()
        )
        stats["scanned"] = len(subjects)

        to_delete = []          # Subject rows to remove
        to_update = []          # (Subject, new_name) for numeric -> category
        seen_per_user = set()   # (user_id, normalized_name) already kept

        for subject in subjects:
            raw = (subject.subject_name or "").strip()

            # 1) Empty / whitespace-only names: nothing to recover.
            if not raw:
                to_delete.append(subject)
                stats["deleted_empty"] += 1
                logger.debug("user %s: drop empty subject id=%s", subject.user_id, subject.id)
                continue

            # 2) Purely numeric names: map to category or delete.
            if raw.isdigit():
                mapped = None if delete_numbers else NUMBER_TO_NAME.get(raw)
                if mapped:
                    effective_name = mapped
                    to_update.append((subject, mapped))
                    stats["mapped"] += 1
                    logger.debug("user %s: map '%s' -> '%s'", subject.user_id, raw, mapped)
                else:
                    to_delete.append(subject)
                    stats["deleted_numeric"] += 1
                    logger.debug("user %s: drop numeric subject '%s' id=%s", subject.user_id, raw, subject.id)
                    continue
            else:
                effective_name = raw

            # 3) Deduplicate (case-insensitive) among surviving rows.
            key = (subject.user_id, effective_name.lower())
            if key in seen_per_user:
                # Was this row queued for a name update? Undo it; it's going away.
                if to_update and to_update[-1][0] is subject:
                    to_update.pop()
                    stats["mapped"] -= 1
                to_delete.append(subject)
                stats["deleted_duplicate"] += 1
                logger.debug("user %s: drop duplicate '%s' id=%s", subject.user_id, effective_name, subject.id)
            else:
                seen_per_user.add(key)

        # Report
        logger.info("Scanned %s subject rows.", stats["scanned"])
        logger.info("  mapped number -> category : %s", stats["mapped"])
        logger.info("  delete (empty name)       : %s", stats["deleted_empty"])
        logger.info("  delete (numeric, unmapped): %s", stats["deleted_numeric"])
        logger.info("  delete (duplicate)        : %s", stats["deleted_duplicate"])

        if not apply_changes:
            logger.info("DRY-RUN: no changes written. Re-run with --apply to commit.")
            session.rollback()
            return stats

        for subject, new_name in to_update:
            subject.subject_name = new_name
        for subject in to_delete:
            session.delete(subject)

        session.commit()
        logger.info("Applied: %s updated, %s deleted.",
                    len(to_update), len(to_delete))
        return stats
    except Exception as e:
        session.rollback()
        logger.error("Error cleaning up subjects: %s", e)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Commit the changes (default is a dry-run preview).")
    parser.add_argument("--delete-numbers", action="store_true",
                        help="Delete numeric subject names instead of mapping them to categories.")
    args = parser.parse_args()

    cleanup_subjects(apply_changes=args.apply, delete_numbers=args.delete_numbers)
