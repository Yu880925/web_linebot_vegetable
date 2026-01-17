# 蔬菜小幫手 LINE Bot
智能蔬菜辨識、價格監控、營養查詢與食譜推薦的 LINE Bot

# 快速啟動
1. Clone 專案
bashgit clone https://github.com/yourusername/vegbot.git
cd vegbot
2. 環境變數設定
建立 .env 檔案：
env# LINE Bot
LINE_CHANNEL_ACCESS_TOKEN=your_token
LINE_CHANNEL_SECRET=your_secret

# Database
DATABASE_URL=postgresql://user:pass@host:5432/db

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET_NAME=veg-data-bucket

# URLs
url_5000=http://localhost:5000
url_9000=http://localhost:9000
FAST_API_URL=http://your-llm-service:8000
3. 啟動服務
bashdocker-compose up -d
4. 檢查狀態
bashdocker-compose ps
docker-compose logs -f linebot_app
服務端口

Flask App: http://localhost:5000
Redis: 6379
MinIO API: http://localhost:9000
MinIO Console: http://localhost:9001

# 本地開發
bash# 建立虛擬環境
python -m venv venv
source venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 啟動外部服務
docker-compose up -d redis minio

# 執行應用程式
python app.py
設定 LINE Webhook
使用 ngrok 建立公開 URL：
bashngrok http 5000
將 ngrok 提供的 HTTPS URL 設定到 LINE Developer Console：
https://your-ngrok-url.ngrok.io/callback
專案結構
vegbot/
├── app.py                 # Flask 主程式
├── docker-compose.yml     # Docker 配置
├── requirements.txt       # Python 依賴
├── rec_veg/              # 蔬菜辨識模組
├── nutri_rec/            # 營養查詢模組
└── redis_client.py       # Redis 連線
