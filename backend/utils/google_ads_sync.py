"""
Google Ads data sync.

Pulls daily account-level and campaign-level metrics
and stores in the metrics table via metrics_db.
"""

from datetime import datetime, timezone, timedelta

from utils.google_auth import get_google_ads_client
from utils.metrics_db import bulk_upsert_metrics, save_sync_log


def _micros(value):
    """Convert micros to currency units."""
    return value / 1_000_000 if value else 0.0


def sync_google_ads_data(client_id: int, customer_id: str, days_back: int = 90) -> dict:
    """Pull daily spend, clicks, impressions, conversions from Google Ads."""
    try:
        customer_id = customer_id.replace("-", "")
        ads_client = get_google_ads_client(customer_id)
        ga_service = ads_client.get_service("GoogleAdsService")

        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

        query = f"""
            SELECT
                segments.date,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_per_conversion
            FROM customer
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY segments.date ASC
        """

        stream = ga_service.search_stream(customer_id=customer_id, query=query)

        metrics_rows = []
        for batch in stream:
            for row in batch.results:
                date = row.segments.date
                cost = _micros(row.metrics.cost_micros)
                avg_cpc = _micros(row.metrics.average_cpc)
                cpc = _micros(row.metrics.cost_per_conversion) if row.metrics.cost_per_conversion else 0.0

                for metric_type, value in [
                    ("cost", cost),
                    ("impressions", row.metrics.impressions),
                    ("clicks", row.metrics.clicks),
                    ("conversions", row.metrics.conversions),
                    ("conversion_value", row.metrics.conversions_value),
                    ("ctr", row.metrics.ctr),
                    ("average_cpc", avg_cpc),
                    ("cost_per_conversion", cpc),
                ]:
                    metrics_rows.append({
                        "client_id": client_id,
                        "source": "google_ads",
                        "metric_type": metric_type,
                        "dimension": "total",
                        "value": float(value),
                        "date": date,
                    })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "google_ads", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "google_ads", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}


def sync_google_ads_campaigns(client_id: int, customer_id: str, days_back: int = 90) -> dict:
    """Pull campaign-level daily breakdown from Google Ads."""
    try:
        customer_id = customer_id.replace("-", "")
        ads_client = get_google_ads_client(customer_id)
        ga_service = ads_client.get_service("GoogleAdsService")

        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

        query = f"""
            SELECT
                campaign.id, campaign.name, campaign.status,
                segments.date,
                metrics.impressions, metrics.clicks,
                metrics.cost_micros, metrics.conversions,
                metrics.conversions_value
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
                AND campaign.status != 'REMOVED'
            ORDER BY segments.date ASC
        """

        stream = ga_service.search_stream(customer_id=customer_id, query=query)

        metrics_rows = []
        for batch in stream:
            for row in batch.results:
                date = row.segments.date
                campaign_name = row.campaign.name
                dim = f"campaign:{campaign_name}"
                cost = _micros(row.metrics.cost_micros)

                for metric_type, value in [
                    ("cost", cost),
                    ("impressions", row.metrics.impressions),
                    ("clicks", row.metrics.clicks),
                    ("conversions", row.metrics.conversions),
                    ("conversion_value", row.metrics.conversions_value),
                ]:
                    metrics_rows.append({
                        "client_id": client_id,
                        "source": "google_ads",
                        "metric_type": metric_type,
                        "dimension": dim,
                        "value": float(value),
                        "date": date,
                    })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "google_ads_campaigns", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "google_ads_campaigns", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}
