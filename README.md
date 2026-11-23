# Lab 18 · Dự báo thời tiết Hà Nội từ Open-Meteo → GCS → BigQuery

Pipeline ETL lấy dự báo nhiệt độ và độ ẩm của Hà Nội theo giờ. Python lưu phản hồi JSON gốc lên Google Cloud Storage (GCS), đọc lại JSON để tạo CSV, rồi nạp CSV vào BigQuery để truy vấn bằng SQL.

| Bước | Đọc từ đâu? | Ghi vào đâu? |
|---|---|---|
| **Extract** | API Open-Meteo | JSON gốc trong `raw/` trên GCS |
| **Transform** | JSON trong `raw/` trên GCS | CSV trong `processed/` trên GCS, mỗi giờ một dòng |
| **Load** | CSV trong `processed/` trên GCS | Bảng `hanoi_hourly_weather` trong BigQuery |

Python chạy trên máy cá nhân. GCS giữ cả bản gốc và bản đã xử lý. Có thể dùng lại JSON gốc để xử lý mà không cần gọi API lần nữa. Dữ liệu trong bài là **dự báo**, với cấu hình mặc định lấy một ngày theo giờ Việt Nam.

## Các file

| File | Vai trò |
|---|---|
| `main.py` | Chạy lần lượt `extract()`, `transform()` và `load()` |
| `requirements.txt` | Danh sách thư viện Python cần cài |
| `.env.example` | Mẫu cấu hình để tạo `.env` trên máy |

## Bước 1 · Cài đặt

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

## Bước 2 · Chuẩn bị Google Cloud

1. Tạo một **bucket private** trong Cloud Storage. Chọn vùng **Singapore (`asia-southeast1`)**, bật **Uniform bucket-level access** và **Public access prevention**.
2. Tạo dataset BigQuery `lesson18_sinh_quang` trong cùng project và cùng vùng **`asia-southeast1`**. Khi chạy thành công, script sẽ tạo bảng `hanoi_hourly_weather` nếu bảng chưa tồn tại.
3. Vào **IAM & Admin → Service Accounts**, tạo service account `lesson18-weather-etl`, rồi vào **Keys → Add key → Create new key → JSON**. Lưu key ngoài thư mục bài nộp.
4. Cấp quyền cho email của service account theo phạm vi sau.

| Phạm vi cấp quyền | Vai trò | Dùng để |
|---|---|---|
| Bucket GCS | **Storage Object User** | Upload JSON, đọc lại JSON và upload CSV |
| Project Google Cloud | **BigQuery Job User** | Tạo và chạy tác vụ nạp dữ liệu |
| Dataset `lesson18_sinh_quang` | **BigQuery Data Editor** | Tạo hoặc cập nhật bảng đích |

## Bước 3 · Điền `.env`

```dotenv
# Thay bằng Project ID, tên bucket và đường dẫn key thật trên máy
GCP_PROJECT_ID=YOUR_PROJECT_ID
GCS_BUCKET=YOUR_BUCKET_NAME
GOOGLE_APPLICATION_CREDENTIALS=/home/your-user/gcp-keys/lesson18-weather-etl.json
GCS_PREFIX=etl_lab/open_meteo/hanoi

# Open-Meteo
OPEN_METEO_URL=https://api.open-meteo.com/v1/forecast
WEATHER_CITY=Hanoi
WEATHER_LATITUDE=21.0285
WEATHER_LONGITUDE=105.8542
WEATHER_TIMEZONE=Asia/Ho_Chi_Minh
WEATHER_FORECAST_DAYS=1
WEATHER_HOURLY=temperature_2m,relative_humidity_2m

# BigQuery
BQ_LOCATION=asia-southeast1
BQ_DATASET=lesson18_sinh_quang
BQ_TABLE=hanoi_hourly_weather
```

`GCS_BUCKET` chỉ chứa tên bucket. `GOOGLE_APPLICATION_CREDENTIALS` chứa đường dẫn tuyệt đối đến file key JSON. Open-Meteo không cần API key cho bài lab này. Giữ `.env` và key JSON trên máy cá nhân, tránh đưa chúng lên Git hoặc vào thư mục bài nộp.

## Bước 4 · Chạy pipeline

```bash
python main.py
```

Script in các mốc `[1]`, `[2]`, `[3]`. Trong Cloud Storage Console, mở bucket rồi vào `etl_lab/open_meteo/hanoi` để xem hai file:

- `raw/hanoi_weather_<run_id>.json` giữ nguyên phản hồi Open-Meteo.
- `processed/hanoi_weather_<run_id>.csv` chứa bảng dự báo theo giờ.

| Cột CSV | Lấy từ đâu? | Kiểu BigQuery |
|---|---|---|
| `city` | `WEATHER_CITY` trong `.env` | `STRING` |
| `forecast_time_local` | `hourly.time` trong JSON, định dạng lại thành `YYYY-MM-DD HH:MM:SS` | `DATETIME` |
| `temperature_c` | `hourly.temperature_2m` trong JSON | `FLOAT64` |
| `humidity_pct` | `hourly.relative_humidity_2m` trong JSON | `INT64` |
| `weather_timezone` | `WEATHER_TIMEZONE` trong `.env` | `STRING` |

Mỗi lần chạy tạo một cặp JSON/CSV mới có chung `run_id`. BigQuery dùng schema khai báo trong `main.py` và `WRITE_TRUNCATE`, nên khi nạp thành công, bảng chứa dữ liệu của lần nạp mới nhất. Muốn chạy thử riêng hai bước GCS, có thể để trống `BQ_DATASET`. Khi chạy đầy đủ để nộp bài, điền lại tên dataset.

## Bước 5 · Kiểm tra trong BigQuery

Mở bảng `lesson18_sinh_quang.hanoi_hourly_weather` và chọn **Preview**, hoặc chạy [queries.sql](queries.sql) sau khi thay `YOUR_PROJECT_ID` bằng Project ID thật.

Với `WEATHER_FORECAST_DAYS=1`, kết quả kỳ vọng là **24 dòng và 24 giờ khác nhau** cho Hà Nội. `forecast_time_local` là giờ Việt Nam. `BQ_LOCATION=asia-southeast1` là vùng Google Cloud của tác vụ nạp dữ liệu.

## Lỗi thường gặp

| Thông báo | Cách xử lý |
|---|---|
| `KeyError: 'GCP_PROJECT_ID'` hoặc tên biến khác | Kiểm tra `.env` nằm cùng thư mục với `main.py` và có đủ các biến cần dùng |
| `DefaultCredentialsError` | Kiểm tra `GOOGLE_APPLICATION_CREDENTIALS` có trỏ tới đúng file key `.json` đã tải xong |
| `403 ... storage.objects.create` hoặc `storage.objects.get` | Kiểm tra service account trong key có quyền **Storage Object User** trên đúng bucket |
| `403 ... bigquery.jobs.create` | Cấp **BigQuery Job User** cho service account ở cấp project |
| `403` khi tạo hoặc cập nhật bảng | Kiểm tra quyền **BigQuery Data Editor** trên dataset |
| `404 ... Dataset ... was not found` | Kiểm tra Project ID, tên `BQ_DATASET` và vùng `BQ_LOCATION` |
| `400 Client Error` từ Open-Meteo | Kiểm tra tọa độ, múi giờ, số ngày dự báo và tên các biến trong `WEATHER_HOURLY` |

## Nguồn dữ liệu

Dữ liệu dự báo lấy từ [Open-Meteo](https://open-meteo.com/). Tham số truy vấn và cấu trúc phản hồi xem tại [Open-Meteo Forecast API](https://open-meteo.com/en/docs).