"""
Google Analytics 4 data sync.

Pulls sessions, users, pageviews, bounce rate + source/medium breakdown
and stores in the metrics table via metrics_db.
"""

from datetime import datetime, timezone

from utils.google_auth import get_ga4_client
from utils.metrics_db import bulk_upsert_metrics, save_sync_log


def sync_ga4_data(client_id: int, property_id: str, days_back: int = 90) -> dict:
    """Pull daily sessions, users, new users, bounce rate, pageviews from GA4."""
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Dimension, Metric,
        )

        ga_client = get_ga4_client()

        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=f"{days_back}daysAgo", end_date="yesterday")],
            dimensions=[Dimension(name="date")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="totalUsers"),
                Metric(name="newUsers"),
                Metric(name="bounceRate"),
                Metric(name="screenPageViews"),
            ],
        )

        response = ga_client.run_report(request)

        metric_names = ["sessions", "totalUsers", "newUsers", "bounceRate", "screenPageViews"]
        metrics_rows = []
        for row in response.rows:
            # GA4 date format: YYYYMMDD → YYYY-MM-DD
            raw_date = row.dimension_values[0].value
            date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

            for i, name in enumerate(metric_names):
                val = float(row.metric_values[i].value or 0)
                metrics_rows.append({
                    "client_id": client_id,
                    "source": "ga4",
                    "metric_type": name,
                    "dimension": "total",
                    "value": val,
                    "date": date,
                })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "ga4", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "ga4", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}


def sync_ga4_sources(client_id: int, property_id: str, days_back: int = 90) -> dict:
    """Pull sessions by source/channel group from GA4."""
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Dimension, Metric,
        )

        ga_client = get_ga4_client()

        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=f"{days_back}daysAgo", end_date="yesterday")],
            dimensions=[Dimension(name="sessionDefaultChannelGroup")],
            metrics=[Metric(name="sessions")],
        )

        response = ga_client.run_report(request)

        # Use yesterday as date for aggregate source data
        now = datetime.now(timezone.utc)
        date = now.strftime("%Y-%m-%d")

        metrics_rows = []
        for row in response.rows:
            channel = row.dimension_values[0].value
            sessions = float(row.metric_values[0].value or 0)
            metrics_rows.append({
                "client_id": client_id,
                "source": "ga4",
                "metric_type": "sessions",
                "dimension": f"source:{channel}",
                "value": sessions,
                "date": date,
            })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "ga4_sources", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "ga4_sources", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}


def sync_ga4_pages(client_id: int, property_id: str, days_back: int = 90) -> dict:
    """Pull top pages by pageviews and sessions from GA4."""
    try:
        from google.analytics.data_v1beta.types import (
            RunReportRequest, DateRange, Dimension, Metric,
        )

        ga_client = get_ga4_client()

        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=f"{days_back}daysAgo", end_date="yesterday")],
            dimensions=[Dimension(name="pagePath")],
            metrics=[
                Metric(name="screenPageViews"),
                Metric(name="sessions"),
            ],
        )

        response = ga_client.run_report(request)

        now = datetime.now(timezone.utc)
        date = now.strftime("%Y-%m-%d")

        metrics_rows = []
        for row in response.rows:
            page_path = row.dimension_values[0].value
            pageviews = float(row.metric_values[0].value or 0)
            sessions = float(row.metric_values[1].value or 0)
            dim = f"page:{page_path}"
            metrics_rows.append({
                "client_id": client_id,
                "source": "ga4",
                "metric_type": "screenPageViews",
                "dimension": dim,
                "value": pageviews,
                "date": date,
            })
            metrics_rows.append({
                "client_id": client_id,
                "source": "ga4",
                "metric_type": "sessions",
                "dimension": dim,
                "value": sessions,
                "date": date,
            })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "ga4_pages", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "ga4_pages", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}
