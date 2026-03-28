"""
Google API authentication — shared service account for GSC, GA4, Sheets, Ads.

Loads credentials from GOOGLE_SERVICE_ACCOUNT_JSON (JSON string) or
GOOGLE_SERVICE_ACCOUNT_PATH (file path). One service account covers all APIs.
"""

import os
import json
import tempfile

from google.oauth2 import service_account
from googleapiclient.discovery import build


def _get_credentials(scopes: list[str]):
    """Load service account credentials with the given scopes."""
    json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "")

    if json_str:
        info = json.loads(json_str)
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)

    if json_path:
        return service_account.Credentials.from_service_account_file(json_path, scopes=scopes)

    raise RuntimeError(
        "No Google credentials configured. Set GOOGLE_SERVICE_ACCOUNT_JSON "
        "or GOOGLE_SERVICE_ACCOUNT_PATH environment variable."
    )


def get_gsc_service():
    """Build and return a Google Search Console API client."""
    creds = _get_credentials(["https://www.googleapis.com/auth/webmasters.readonly"])
    return build("searchconsole", "v1", credentials=creds)


def get_ga4_client():
    """Build and return a GA4 Data API client."""
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    creds = _get_credentials(["https://www.googleapis.com/auth/analytics.readonly"])
    return BetaAnalyticsDataClient(credentials=creds)


def get_sheets_service():
    """Build and return a Google Sheets API v4 client."""
    creds = _get_credentials(["https://www.googleapis.com/auth/spreadsheets.readonly"])
    return build("sheets", "v4", credentials=creds)


def get_google_ads_client(customer_id: str):
    """Build and return a Google Ads API client using service account."""
    from google.ads.googleads.client import GoogleAdsClient

    json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "")

    # google-ads library needs a file path
    if json_str and not json_path:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        tmp.write(json_str)
        tmp.close()
        json_path = tmp.name

    config = {
        "developer_token": os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
        "json_key_file_path": json_path,
        "login_customer_id": os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", ""),
    }
    config = {k: v for k, v in config.items() if v}

    return GoogleAdsClient.load_from_dict(config, version="v23")


def init_meta_ads(ad_account_id: str):
    """Initialize Meta Marketing API and return AdAccount object."""
    from facebook_business.api import FacebookAdsApi
    from facebook_business.adobjects.adaccount import AdAccount

    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")
    access_token = os.environ.get("META_ACCESS_TOKEN", "")

    if not access_token:
        raise RuntimeError(
            "No Meta credentials configured. Set META_ACCESS_TOKEN environment variable."
        )

    FacebookAdsApi.init(app_id, app_secret, access_token)
    return AdAccount(f"act_{ad_account_id}" if not ad_account_id.startswith("act_") else ad_account_id)
