"""
Google Sheets data sync.

Pulls client-tracked metrics (leads, calls, revenue, etc.) from
a configured Google Sheet and stores in the metrics table via metrics_db.
"""

from datetime import datetime, timedelta

from utils.google_auth import get_sheets_service
from utils.metrics_db import bulk_upsert_metrics, save_sync_log


def _col_index(letter: str, base: str) -> int:
    """Convert column letter to index relative to base column."""
    return ord(letter.upper()) - ord(base.upper())


def _parse_date(raw_date, date_format: str) -> str:
    """Parse a date value from a sheet cell. Handles serial numbers and strings."""
    if isinstance(raw_date, (int, float)):
        # Google Sheets serial date number (days since 1899-12-30)
        base = datetime(1899, 12, 30)
        parsed = base + timedelta(days=int(raw_date))
        return parsed.strftime("%Y-%m-%d")
    return datetime.strptime(str(raw_date).strip(), date_format).strftime("%Y-%m-%d")


def sync_sheets_data(client_id: int, sheets_config: dict) -> dict:
    """Pull client metrics from their Google Sheet into the metrics table."""
    try:
        service = get_sheets_service()
        spreadsheet_id = sheets_config["spreadsheet_id"]
        sheet_name = sheets_config.get("sheet_name", "Sheet1")
        date_col = sheets_config.get("date_column", "A")
        date_fmt = sheets_config.get("date_format", "%m/%d/%Y")
        data_start = sheets_config.get("data_start_row", 2)
        metric_configs = sheets_config.get("metrics", [])

        if not metric_configs:
            return {"status": "error", "message": "No metrics configured"}

        # Build range: from date column to last metric column
        all_cols = [date_col] + [m["column"] for m in metric_configs]
        min_col = min(all_cols, key=lambda c: ord(c.upper()))
        max_col = max(all_cols, key=lambda c: ord(c.upper()))
        range_name = f"'{sheet_name}'!{min_col}{data_start}:{max_col}"

        rows = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        ).execute().get("values", [])

        date_idx = _col_index(date_col, min_col)
        metrics_rows = []

        for row in rows:
            if len(row) <= date_idx:
                continue

            raw_date = row[date_idx]
            if raw_date is None or raw_date == "":
                continue

            try:
                date_str = _parse_date(raw_date, date_fmt)
            except (ValueError, TypeError):
                continue

            for mc in metric_configs:
                idx = _col_index(mc["column"], min_col)
                if idx < len(row) and row[idx] not in (None, ""):
                    try:
                        val = float(row[idx])
                    except (ValueError, TypeError):
                        continue
                    metrics_rows.append({
                        "client_id": client_id,
                        "source": "sheets",
                        "metric_type": mc["metric_type"],
                        "dimension": mc.get("dimension", "total"),
                        "value": val,
                        "date": date_str,
                    })

        written = bulk_upsert_metrics(metrics_rows)
        save_sync_log(client_id, "sheets", "success", rows_synced=written)
        return {"status": "success", "rows": written}

    except Exception as e:
        save_sync_log(client_id, "sheets", "error", error_msg=str(e))
        return {"status": "error", "message": str(e)}
