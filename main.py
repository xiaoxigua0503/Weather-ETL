import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from google.cloud import bigquery, storage


def extract(bucket, raw_path):
    """Gọi Open-Meteo và lưu nguyên phản hồi JSON lên GCS."""
    response = requests.get(
        os.environ["OPEN_METEO_URL"],
        params={
            "latitude": os.environ["WEATHER_LATITUDE"],
            "longitude": os.environ["WEATHER_LONGITUDE"],
            "hourly": os.environ["WEATHER_HOURLY"],
            "timezone": os.environ["WEATHER_TIMEZONE"],
            "forecast_days": os.environ["WEATHER_FORECAST_DAYS"],
        },
        timeout=30,
    )
    response.raise_for_status()

    bucket.blob(raw_path).upload_from_string(
        response.content,
        content_type="application/json",
    )
    print(f"[1] Đã lưu JSON gốc → gs://{bucket.name}/{raw_path}")


def transform(bucket, raw_path, csv_path):
    """Ghép thời gian, nhiệt độ và độ ẩm thành từng dòng theo giờ."""
    data = json.loads(bucket.blob(raw_path).download_as_text())
    hourly = data["hourly"]

    df = pd.DataFrame(
        {
            "city": os.environ["WEATHER_CITY"],
            "forecast_time_local": pd.to_datetime(hourly["time"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "temperature_c": hourly["temperature_2m"],
            "humidity_pct": pd.array(hourly["relative_humidity_2m"], dtype="Int64"),
            "weather_timezone": os.environ["WEATHER_TIMEZONE"],
        }
    )
    if df.empty:
        raise ValueError("Open-Meteo không trả về dữ liệu dự báo theo giờ.")

    print(df.head().to_string(index=False))
    bucket.blob(csv_path).upload_from_string(
        df.to_csv(index=False),
        content_type="text/csv",
    )
    print(f"[2] Đã lưu CSV {len(df)} dòng → gs://{bucket.name}/{csv_path}")


def load(project, bucket_name, csv_path, dataset):
    """Nạp CSV vào BigQuery và thay dữ liệu của lần chạy trước."""
    table_name = os.getenv("BQ_TABLE", "hanoi_hourly_weather")
    table = f"{project}.{dataset}.{table_name}"
    location = os.getenv("BQ_LOCATION", "asia-southeast1")

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=[
            bigquery.SchemaField("city", "STRING"),
            bigquery.SchemaField("forecast_time_local", "DATETIME"),
            bigquery.SchemaField("temperature_c", "FLOAT64"),
            bigquery.SchemaField("humidity_pct", "INT64"),
            bigquery.SchemaField("weather_timezone", "STRING"),
        ],
    )

    client = bigquery.Client(project=project, location=location)
    job = client.load_table_from_uri(
        f"gs://{bucket_name}/{csv_path}",
        table,
        job_config=job_config,
    )
    job.result()
    print(f"[3] Đã nạp BigQuery → {table} ({job.output_rows} dòng)")


def main():
    load_dotenv(Path(__file__).with_name(".env"))

    project = os.environ["GCP_PROJECT_ID"]
    bucket_name = os.environ["GCS_BUCKET"]
    prefix = os.getenv("GCS_PREFIX", "etl_lab/open_meteo/hanoi").strip("/")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    raw_path = f"{prefix}/raw/hanoi_weather_{run_id}.json"
    csv_path = f"{prefix}/processed/hanoi_weather_{run_id}.csv"

    bucket = storage.Client(project=project).bucket(bucket_name)
    extract(bucket, raw_path)
    transform(bucket, raw_path, csv_path)

    dataset = os.getenv("BQ_DATASET", "").strip()
    if dataset:
        load(project, bucket_name, csv_path, dataset)
    else:
        print("[3] Bỏ qua BigQuery vì BQ_DATASET đang trống.")


if __name__ == "__main__":
    main()