"""
Google Search Console data sync.

Pulls clicks, impressions, CTR, avg position + per-keyword rankings
and stores in the metrics table via metrics_db.
"""

import re
from datetime import datetime, timezone, timedelta

from utils.google_auth import get_gsc_service
from utils.metrics_db import bulk_upsert_metrics, save_sync_log


def _clean_domain(domain: str) -> str:
    """Strip protocol, www, trailing slash from domain."""
    d = re.sub(r'^https?://', '', domain)
    d = re.sub(r'^www\.', '', d)
    return d.rstrip('/')


def _date_range(days_back: int) -> tuple[str, str]:
    """Return (start_date, end_date) strings. End is 3 days ago (GSC data delay)."""
    now = datetime.now(timezone.utc)
    end = now - timedelta(days=3)
    start = now - timedelta(days=days_back)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def sync_gsc_data(client_id: int, domain: str, days_back: int = 90) -> dict:
    """Pull daily aggregate clicks, impressions, CTR, position from GSC."""
    try:
        service = get_gsc_service()
        site_url = f"sc-domain:{_clean_domain(domain)}"
        start_date, end_date = _date_range(days_back)

        response = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["date"],
                "rowLimit": 25000,
            },
        ).execute()

        rows_data = response.get("rows", [])
        metrics_rows = []
        for row in rows_data:
            date = row["keys"][0]
            for metric, key in [
                ("clicks", "clicks"),
                ("impressions", "impressions"),
                ("ctr", "ctr"),
                ("position", "position"),
            ]:
                metrics_rows.append({
                    "client_id": client_id,
                    "source": "gsc",
                    "metric_type": metric,
                    "dimension": "total",
                    "value": row[key],
                    "date": date,
                })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "gsc", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "gsc", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}


def sync_gsc_keywords(client_id: int, domain: str, days_back: int = 90) -> dict:
    """Pull per-keyword daily positions, clicks, impressions from GSC."""
    try:
        service = get_gsc_service()
        site_url = f"sc-domain:{_clean_domain(domain)}"
        start_date, end_date = _date_range(days_back)

        all_rows = []
        start_row = 0
        while True:
            response = service.searchanalytics().query(
                siteUrl=site_url,
                body={
                    "startDate": start_date,
                    "endDate": end_date,
                    "dimensions": ["query", "date"],
                    "rowLimit": 25000,
                    "startRow": start_row,
                },
            ).execute()

            batch = response.get("rows", [])
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < 25000:
                break
            start_row += len(batch)

        metrics_rows = []
        for row in all_rows:
            query, date = row["keys"]
            dim = f"query:{query}"
            for metric, key in [
                ("position", "position"),
                ("clicks", "clicks"),
                ("impressions", "impressions"),
            ]:
                metrics_rows.append({
                    "client_id": client_id,
                    "source": "gsc",
                    "metric_type": metric,
                    "dimension": dim,
                    "value": row[key],
                    "date": date,
                })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "gsc_keywords", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "gsc_keywords", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}


def sync_gsc_pages(client_id: int, domain: str, days_back: int = 90) -> dict:
    """Pull top pages by clicks/impressions from GSC (aggregate, no date dim)."""
    try:
        service = get_gsc_service()
        site_url = f"sc-domain:{_clean_domain(domain)}"
        start_date, end_date = _date_range(days_back)

        response = service.searchanalytics().query(
            siteUrl=site_url,
            body={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["page"],
                "rowLimit": 25000,
            },
        ).execute()

        rows_data = response.get("rows", [])
        metrics_rows = []
        # Use end_date as the date for aggregate page data
        for row in rows_data:
            page_url = row["keys"][0]
            dim = f"page:{page_url}"
            for metric, key in [("clicks", "clicks"), ("impressions", "impressions")]:
                metrics_rows.append({
                    "client_id": client_id,
                    "source": "gsc",
                    "metric_type": metric,
                    "dimension": dim,
                    "value": row[key],
                    "date": end_date,
                })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "gsc_pages", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "gsc_pages", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}
