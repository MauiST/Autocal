"""
Certificate Loader
==================
Standalone tool to load sensor serials from the Sensors table
into MeasTemp by CertificateNo, split into batches of up to 6.

Run independently:
    python tools/cert_loader.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from db.connection import connect_db
from db.queries import (
    fetch_serials_by_certificate,
    get_current_meastemp,
    get_next_batch_no,
    delete_meastemp,
    insert_batches_into_meastemp
)


def split_into_batches(serials, start_batch=1):
    """
    Split serials into batches of up to 6.
    Last batch can be smaller.
    New certificates always start in a fresh batch.
    Returns dict {batch_no: [serials]}
    """
    batches  = {}
    batch_no = start_batch
    for i in range(0, len(serials), 6):
        batches[batch_no] = serials[i:i + 6]
        batch_no += 1
    return batches


def print_meastemp_summary(conn):
    rows = get_current_meastemp(conn)
    if not rows:
        print("  MeasTemp is empty.")
        return
    current_batch = None
    for batch_no, serial in rows:
        if batch_no != current_batch:
            current_batch = batch_no
            print(f"\n  Batch {batch_no}:")
        print(f"    {serial}")
    print()


def main():
    print('\n' + '='*55)
    print('  CERTIFICATE LOADER')
    print('='*55)

    try:
        conn = connect_db()
        if not conn:
            print("  ERROR: Could not connect to database.")
            return
        print("  DB connected OK")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    while True:
        print('\n' + '-'*55)
        cert_no = input("  Enter CertificateNo (or Q to quit): ").strip()
        if cert_no.upper() == 'Q':
            break

        serials = fetch_serials_by_certificate(conn, cert_no)
        if not serials:
            print(f"  No serials found for CertificateNo '{cert_no}'.")
            continue

        print(f"\n  Found {len(serials)} serial(s) for Certificate {cert_no}:")
        for s in serials:
            print(f"    {s}")

        current = get_current_meastemp(conn)
        if current:
            print(f"\n  MeasTemp currently contains {len(current)} serial(s):")
            print_meastemp_summary(conn)

            while True:
                action = input(
                    "  Delete existing list and replace (D) or Add to list (A)? "
                ).strip().upper()
                if action in ['D', 'A']:
                    break
                print("  Please enter D or A.")

            if action == 'D':
                delete_meastemp(conn)
                start_batch = 1
            else:
                start_batch = get_next_batch_no(conn)
                print(f"  Adding -- starting at Batch {start_batch}.")
        else:
            print("\n  MeasTemp is empty, loading directly.")
            start_batch = 1

        batches = split_into_batches(serials, start_batch)
        insert_batches_into_meastemp(conn, batches)
        print(f"\n  MeasTemp updated -- current contents:")
        print_meastemp_summary(conn)

        while True:
            another = input("  Load another CertificateNo? (y/n): ").strip().lower()
            if another in ['y', 'n']:
                break
            print("  Please enter y or n.")
        if another == 'n':
            break

    conn.close()
    print("\n  Done. DB connection closed.")


if __name__ == "__main__":
    main()
