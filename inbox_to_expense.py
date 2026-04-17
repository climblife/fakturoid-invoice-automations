#!/usr/bin/env python3
"""Inbox → Expense workflow for Fakturoid (ClimbLife).

Subcommands:
  list              list all files in the Krabice (inbox) with metadata
  fetch             download the first file from the Krabice (convenience)
  download --id N   download a specific inbox file by id into tmp/
  create --data F   create a fully-filled, paid Expense from F (JSON), attach
                    one or more inbox files to it, then delete those files
                    from the Krabice
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

API_BASE = "https://app.fakturoid.cz/api/v3"
USER_AGENT = "ClimbLife Invoicing (m.majsky@gmail.com)"
TMP_DIR = Path("tmp")


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def get_token() -> str:
    load_dotenv()
    client_id = os.environ.get("FAKTUROID_CLIENT_ID")
    client_secret = os.environ.get("FAKTUROID_CLIENT_SECRET")
    if not client_id or not client_secret:
        die("Missing FAKTUROID_CLIENT_ID / FAKTUROID_CLIENT_SECRET in .env")
    r = requests.post(
        f"{API_BASE}/oauth/token",
        auth=(client_id, client_secret),
        json={"grant_type": "client_credentials"},
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=30,
    )
    if r.status_code != 200:
        die(f"Token request failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }


def get_slug(token: str) -> str:
    forced = os.environ.get("FAKTUROID_SLUG")
    if forced:
        return forced
    r = requests.get(f"{API_BASE}/user.json", headers=auth_headers(token), timeout=30)
    if r.status_code != 200:
        die(f"/user.json failed: {r.status_code} {r.text}")
    accounts = r.json().get("accounts", [])
    if not accounts:
        die("No accounts returned for this token")
    if len(accounts) > 1:
        slugs = ", ".join(a.get("slug", "?") for a in accounts)
        die(f"Multiple accounts ({slugs}); set FAKTUROID_SLUG in .env to pin one")
    return accounts[0]["slug"]


def list_inbox_files(token: str, slug: str) -> list:
    out = []
    page = 1
    while True:
        r = requests.get(
            f"{API_BASE}/accounts/{slug}/inbox_files.json",
            headers=auth_headers(token),
            params={"page": page},
            timeout=30,
        )
        if r.status_code != 200:
            die(f"Inbox list failed: {r.status_code} {r.text}")
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 40:
            break
        page += 1
        if page > 20:
            break
    return out


def download_inbox_file(token: str, slug: str, inbox_id: int, filename: str) -> Path:
    TMP_DIR.mkdir(exist_ok=True)
    local_path = TMP_DIR / f"{inbox_id}__{filename}"
    dl = requests.get(
        f"{API_BASE}/accounts/{slug}/inbox_files/{inbox_id}/download",
        headers=auth_headers(token),
        timeout=60,
    )
    if dl.status_code != 200:
        die(f"Download failed: {dl.status_code} {dl.text}")
    local_path.write_bytes(dl.content)
    return local_path


def cmd_list(args: argparse.Namespace) -> None:
    token = get_token()
    slug = get_slug(token)
    files = list_inbox_files(token, slug)
    print(json.dumps({
        "slug": slug,
        "count": len(files),
        "files": [
            {
                "inbox_id": f["id"],
                "filename": f["filename"],
                "bytes": f.get("bytesize"),
                "ocr_status": f.get("ocr_status"),
                "created_at": f.get("created_at"),
            }
            for f in files
        ],
    }, ensure_ascii=False, indent=2))


def cmd_fetch(args: argparse.Namespace) -> None:
    token = get_token()
    slug = get_slug(token)
    files = list_inbox_files(token, slug)
    if not files:
        print(json.dumps({"empty": True, "slug": slug}))
        return

    f = files[0]
    local_path = download_inbox_file(token, slug, f["id"], f["filename"])
    print(json.dumps({
        "slug": slug,
        "inbox_id": f["id"],
        "filename": f["filename"],
        "local_path": str(local_path),
        "bytes": local_path.stat().st_size,
        "ocr_status": f.get("ocr_status"),
    }, ensure_ascii=False, indent=2))


def cmd_download(args: argparse.Namespace) -> None:
    token = get_token()
    slug = get_slug(token)
    files = list_inbox_files(token, slug)
    match = next((f for f in files if f["id"] == args.id), None)
    if not match:
        die(f"Inbox file id={args.id} not found in Krabice")
    local_path = download_inbox_file(token, slug, match["id"], match["filename"])
    print(json.dumps({
        "slug": slug,
        "inbox_id": match["id"],
        "filename": match["filename"],
        "local_path": str(local_path),
        "bytes": local_path.stat().st_size,
        "ocr_status": match.get("ocr_status"),
    }, ensure_ascii=False, indent=2))


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def _normalize(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def list_all_subjects(token: str, slug: str) -> list:
    out = []
    page = 1
    while True:
        r = requests.get(
            f"{API_BASE}/accounts/{slug}/subjects.json",
            headers=auth_headers(token),
            params={"page": page},
            timeout=30,
        )
        if r.status_code != 200:
            die(f"Subjects list failed: {r.status_code} {r.text}")
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 40:
            break
        page += 1
        if page > 20:
            break
    return out


def find_or_create_subject(token: str, slug: str, supplier: dict) -> tuple[int, bool]:
    name = (supplier.get("name") or "").strip()
    reg = (supplier.get("registration_no") or "").strip()
    vat = (supplier.get("vat_no") or "").strip()
    if not name and not reg:
        die("supplier needs at least name or registration_no")

    if reg:
        r = requests.get(
            f"{API_BASE}/accounts/{slug}/subjects/search.json",
            headers=auth_headers(token),
            params={"query": reg},
            timeout=30,
        )
        if r.status_code != 200:
            die(f"Subject search (reg) failed: {r.status_code} {r.text}")
        for s in r.json():
            if (s.get("registration_no") or "").strip() == reg:
                return s["id"], False

    subjects = list_all_subjects(token, slug)
    target = _normalize(name)
    if target:
        for s in subjects:
            if _normalize(s.get("name") or "") == target:
                return s["id"], False
            if _normalize(s.get("full_name") or "") == target:
                return s["id"], False
        for s in subjects:
            candidate = _normalize(s.get("name") or "")
            if candidate and (target in candidate or candidate in target):
                return s["id"], False

    payload = {"name": name or reg}
    if reg:
        payload["registration_no"] = reg
        payload["setting_update_from_ares"] = "on"
    if vat:
        payload["vat_no"] = vat
    cr = requests.post(
        f"{API_BASE}/accounts/{slug}/subjects.json",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if cr.status_code not in (200, 201):
        die(f"Subject create failed: {cr.status_code} {cr.text}")
    return cr.json()["id"], True


def build_attachment(local_path: Path) -> dict:
    data = local_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    mime = guess_mime(local_path)
    return {
        "filename": local_path.name.split("__", 1)[-1],
        "data_url": f"data:{mime};base64,{b64}",
    }


def normalize_attachments(data: dict) -> list[dict]:
    """Return list of {inbox_id, local_path} dicts.

    Supports legacy single-file shape ({inbox_id, local_path}) and new
    multi-file shape ({attachments: [{inbox_id, local_path}, ...]}).
    Order is preserved — first attachment is considered primary (Invoice
    preferred over Receipt per accountant's preference).
    """
    if data.get("attachments"):
        items = data["attachments"]
    else:
        items = [{"inbox_id": data["inbox_id"], "local_path": data["local_path"]}]
    out = []
    for it in items:
        if not it.get("inbox_id") or not it.get("local_path"):
            die(f"attachment missing inbox_id/local_path: {it}")
        out.append({"inbox_id": int(it["inbox_id"]), "local_path": it["local_path"]})
    return out


def create_expense(token: str, slug: str, data: dict, subject_id: int, attachments: list[dict]) -> dict:
    inbox_ids = ", ".join(str(a["inbox_id"]) for a in attachments)
    payload = {
        "subject_id": subject_id,
        "document_type": data.get("document_type", "invoice"),
        "lines": data["lines"],
        "attachments": [build_attachment(Path(a["local_path"])) for a in attachments],
        "private_note": (
            "Vytvořeno pomocí Claude AI. "
            f"Automaticky z Krabice (inbox_file_ids={inbox_ids})."
        ),
    }
    for key in (
        "original_number", "variable_symbol",
        "issued_on", "received_on", "due_on", "taxable_fulfillment_due",
        "currency", "payment_method", "vat_price_mode", "description",
    ):
        if data.get(key):
            payload[key] = data[key]

    r = requests.post(
        f"{API_BASE}/accounts/{slug}/expenses.json",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if r.status_code not in (200, 201):
        die(f"Expense create failed: {r.status_code} {r.text}")
    return r.json()


def pay_expense(token: str, slug: str, expense_id: int, paid_on: str) -> dict:
    r = requests.post(
        f"{API_BASE}/accounts/{slug}/expenses/{expense_id}/payments.json",
        headers={**auth_headers(token), "Content-Type": "application/json"},
        json={"paid_on": paid_on, "mark_document_as_paid": True},
        timeout=30,
    )
    if r.status_code not in (200, 201):
        die(f"Expense payment failed: {r.status_code} {r.text}")
    return r.json()


def delete_inbox_file(token: str, slug: str, inbox_id: int) -> None:
    r = requests.delete(
        f"{API_BASE}/accounts/{slug}/inbox_files/{inbox_id}.json",
        headers=auth_headers(token),
        timeout=30,
    )
    if r.status_code not in (200, 204):
        die(f"Inbox delete failed: {r.status_code} {r.text}")


def cmd_create(args: argparse.Namespace) -> None:
    with open(args.data, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    for required in ("supplier", "issued_on", "lines"):
        if not data.get(required):
            die(f"data.json missing required field: {required}")

    attachments = normalize_attachments(data)
    paid_on = data.get("paid_on") or data["issued_on"]

    token = get_token()
    slug = get_slug(token)

    subject_id, subject_created = find_or_create_subject(token, slug, data["supplier"])
    expense = create_expense(token, slug, data, subject_id, attachments)
    payment = pay_expense(token, slug, expense["id"], paid_on)
    for a in attachments:
        delete_inbox_file(token, slug, a["inbox_id"])

    print(json.dumps({
        "slug": slug,
        "subject_id": subject_id,
        "subject_created": subject_created,
        "expense_id": expense["id"],
        "expense_number": expense.get("number"),
        "expense_html_url": expense.get("html_url"),
        "paid_on": paid_on,
        "payment_id": payment.get("id"),
        "attached_inbox_ids": [a["inbox_id"] for a in attachments],
        "inbox_deleted": True,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List all files in Krabice").set_defaults(func=cmd_list)
    sub.add_parser("fetch", help="Download first file from Krabice").set_defaults(func=cmd_fetch)

    dp = sub.add_parser("download", help="Download a specific inbox file by id")
    dp.add_argument("--id", type=int, required=True, help="Inbox file id")
    dp.set_defaults(func=cmd_download)

    cp = sub.add_parser("create", help="Create expense from data.json")
    cp.add_argument("--data", required=True, help="Path to data.json")
    cp.set_defaults(func=cmd_create)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
