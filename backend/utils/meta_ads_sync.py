"""
Meta (Facebook/Instagram) Ads data sync.

Pulls daily account-level and campaign-level metrics
and stores in the metrics table via metrics_db.
"""

from datetime import datetime, timezone, timedelta

from utils.google_auth import init_meta_ads
from utils.metrics_db import bulk_upsert_metrics, save_sync_log


def _extract_conversions(insight: dict) -> float:
    """Sum all conversion actions from the actions array."""
    actions = insight.get("actions", [])
    if not actions:
        return 0.0
    total = 0.0
    for a in actions:
        if a.get("action_type", "").startswith("offsite_conversion"):
            total += float(a.get("value", 0))
    # If no offsite conversions, try total actions
    if total == 0.0:
        for a in actions:
            if a.get("action_type") == "lead":
                total += float(a.get("value", 0))
    return total


def _extract_conversion_value(insight: dict) -> float:
    """Sum purchase values from action_values array."""
    action_values = insight.get("action_values", [])
    if not action_values:
        return 0.0
    total = 0.0
    for av in action_values:
        if av.get("action_type", "").startswith("offsite_conversion"):
            total += float(av.get("value", 0))
    return total


def sync_meta_ads_data(client_id: int, ad_account_id: str, days_back: int = 90) -> dict:
    """Pull daily spend, clicks, impressions, conversions from Meta Ads."""
    try:
        from facebook_business.adobjects.adsinsights import AdsInsights

        account = init_meta_ads(ad_account_id)

        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

        params = {
            "time_range": {"since": start_date, "until": end_date},
            "time_increment": 1,
        }
        fields = [
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.ctr,
            AdsInsights.Field.cpc,
            AdsInsights.Field.cpm,
            AdsInsights.Field.actions,
            AdsInsights.Field.action_values,
            AdsInsights.Field.date_start,
        ]

        insights = account.get_insights(params=params, fields=fields)

        metrics_rows = []
        for insight in insights:
            date = insight.get("date_start", "")
            spend = float(insight.get("spend", 0))
            conversions = _extract_conversions(insight)
            conv_value = _extract_conversion_value(insight)
            roas = conv_value / spend if spend > 0 else 0.0

            for metric_type, value in [
                ("spend", spend),
                ("impressions", float(insight.get("impressions", 0))),
                ("clicks", float(insight.get("clicks", 0))),
                ("ctr", float(insight.get("ctr", 0))),
                ("cpc", float(insight.get("cpc", 0))),
                ("cpm", float(insight.get("cpm", 0))),
                ("conversions", conversions),
                ("conversion_value", conv_value),
                ("roas", roas),
            ]:
                metrics_rows.append({
                    "client_id": client_id,
                    "source": "meta_ads",
                    "metric_type": metric_type,
                    "dimension": "total",
                    "value": value,
                    "date": date,
                })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "meta_ads", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "meta_ads", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}


def sync_meta_ads_campaigns(client_id: int, ad_account_id: str, days_back: int = 90) -> dict:
    """Pull campaign-level daily breakdown from Meta Ads."""
    try:
        from facebook_business.adobjects.adsinsights import AdsInsights

        account = init_meta_ads(ad_account_id)

        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

        params = {
            "time_range": {"since": start_date, "until": end_date},
            "time_increment": 1,
            "level": "campaign",
        }
        fields = [
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.campaign_id,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.actions,
            AdsInsights.Field.action_values,
            AdsInsights.Field.date_start,
        ]

        insights = account.get_insights(params=params, fields=fields)

        metrics_rows = []
        for insight in insights:
            date = insight.get("date_start", "")
            campaign_name = insight.get("campaign_name", "Unknown")
            dim = f"campaign:{campaign_name}"
            spend = float(insight.get("spend", 0))
            conversions = _extract_conversions(insight)
            conv_value = _extract_conversion_value(insight)

            for metric_type, value in [
                ("spend", spend),
                ("impressions", float(insight.get("impressions", 0))),
                ("clicks", float(insight.get("clicks", 0))),
                ("conversions", conversions),
                ("conversion_value", conv_value),
            ]:
                metrics_rows.append({
                    "client_id": client_id,
                    "source": "meta_ads",
                    "metric_type": metric_type,
                    "dimension": dim,
                    "value": value,
                    "date": date,
                })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "meta_ads_campaigns", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "meta_ads_campaigns", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}
