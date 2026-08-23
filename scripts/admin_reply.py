#!/usr/bin/env python3
"""Ответ оператора в CRM с корректной UTF-8 (без кракозябр PowerShell).

Usage:
  python scripts/admin_reply.py 2 "Здравствуйте! Оператор на связи."
  python scripts/admin_reply.py --list
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Admin reply to CRM ticket")
    parser.add_argument("ticket_id", nargs="?", type=int, help="Ticket ID")
    parser.add_argument("message", nargs="?", help="Reply text")
    parser.add_argument(
        "--base-url",
        default=os.getenv("OMS_BASE_URL", "http://localhost:8000"),
    )
    parser.add_argument(
        "--user",
        default=os.getenv("ADMIN_BASIC_USER", "admin"),
    )
    parser.add_argument(
        "--password",
        default=os.getenv("ADMIN_BASIC_PASSWORD", "admin_change_me"),
    )
    parser.add_argument("--list", action="store_true", help="List open tickets")
    args = parser.parse_args()

    auth = (args.user, args.password)
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=10.0) as client:
        if args.list:
            resp = client.get("/admin/v1/tickets", auth=auth)
            resp.raise_for_status()
            for row in resp.json():
                print(f"#{row['id']} [{row['status']}] user={row['user_id']} order={row.get('order_id')}")
            return 0

        if args.ticket_id is None or not args.message:
            parser.error("ticket_id and message are required (or use --list)")

        resp = client.post(
            f"/admin/v1/tickets/{args.ticket_id}/reply",
            json={"body": args.message},
            auth=auth,
        )
        resp.raise_for_status()
        print(resp.json())
    return 0


if __name__ == "__main__":
    sys.exit(main())
