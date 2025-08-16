import base64
import logging
import os
import sys
import uuid
from logging.handlers import RotatingFileHandler
import requests
from dotenv import load_dotenv
from flask import Flask, abort, render_template, request, send_from_directory, jsonify, Response, send_file
from flask_cors import CORS
from collections import defaultdict
import psycopg2
import psycopg2.extras # 為了使用 DictCursor
import datetime # 為了取得當前月份
from linebot.exceptions import InvalidSignatureError
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi
from rec_veg.rec_veg_new import rec_veg
from nutri_rec.nutri_rec import (
    get_top_vegetables_by_nutrient,
    get_vegetables_by_name_or_alias,
)
import io
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from linebot.v3.messaging.models import (
    CameraAction,
    CameraRollAction,
    FlexBox,
    FlexBubble,
    FlexButton,
    FlexCarousel,
    FlexImage,
    FlexMessage,
    FlexText,
    ImageMessage,
    MessageAction,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
    TemplateMessage,
    ImageCarouselTemplate,
    ImageCarouselColumn,
    URIAction,
    PostbackAction,
)
from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks.models import (
    ImageMessageContent,
    MessageEvent,
    TextMessageContent,
)
from linebot.v3.webhooks.models import PostbackEvent 
import json 
import re


# 新增日誌以確認 rec_veg 模組載入
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

load_dotenv()

@app.route("/")
def index():
    url_5000 = os.getenv("url_5000", "http://localhost:5000")
    return render_template("index.html", url_5000=url_5000)

@app.route('/search/<veg_id>')
def veg_search(veg_id):
    return send_from_directory('templates', 'index.html')

app.logger.setLevel(logging.INFO)
for handler in app.logger.handlers:
    app.logger.removeHandler(handler)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
app.logger.addHandler(handler)


app.logger.info("Attempting to import rec_veg_new...")
from rec_veg.rec_veg_new import rec_veg
app.logger.info("rec_veg_new imported successfully.")
import pandas as pd

NUTRIENT_DISPLAY_MAPPING = {
    "calories_kcal": "熱量",
    "water_g": "水",
    "protein_g": "蛋白質",
    "fat_g": "脂肪",
    "carb_g": "碳水化合物",
    "fiber_g": "膳食纖維",
    "sugar_g": "糖",
    "sodium_mg": "鈉",
    "potassium_mg": "鉀",
    "calcium_mg": "鈣",
    "magnesium_mg": "鎂",
    "iron_mg": "鐵",
    "zinc_mg": "鋅",
    "phosphorus_mg": "磷",
    "vitamin_a_iu": "維生素A",
    "vitamin_c_mg": "維生素C",
    "vitamin_e_mg": "維生素E",
    "vitamin_b1_mg": "維生素B1",
    "folic_acid_ug": "葉酸",
}
UNIT_ABBREVIATION_TO_CHINESE = {
    "kcal": "大卡",
    "g": "克",
    "mg": "毫克",
    "iu": "IU",
    "ug": "微克",
}

# === 新增：資料庫連線函式 ===
def get_db_connection():
    """建立並回傳 PostgreSQL 資料庫連線"""
    try:
        DATABASE_URL = os.getenv("DATABASE_URL")
        app.logger.info(f"Connecting to database at {DATABASE_URL}")
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        app.logger.error(f"Database connection failed: {e}")
        return None

# MinIO 客戶端設定
def get_minio_client():
    """建立並回傳 MinIO 客戶端"""
    try:
        minio_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("url_9000"),
            aws_access_key_id=os.getenv("MINIO_ROOT_USER"),
            aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD"),
        )
        return minio_client
    except Exception as e:
        app.logger.error(f"Error creating MinIO client: {e}")
        return None


def get_vegetable_seasons(vege_id):
    conn = get_db_connection()
    if not conn:
        return ""
    
    season_mapping = {
        (3, 4, 5): '春季',
        (6, 7, 8): '夏季',
        (9, 10, 11): '秋季',
        (12, 1, 2): '冬季'
    }
    seasons = []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # 查詢所有 fresh_month_XX 欄位
        cur.execute(f"SELECT {' ,'.join([f'fresh_month_{i:02d}' for i in range(1, 13)])} FROM basic_vege WHERE id = %s;", (vege_id,))
        row = cur.fetchone()
        if row:
            for month in range(1, 13):
                month_column = f'fresh_month_{month:02d}'
                if row[month_column] == 1:
                    for months_in_season, season_name in season_mapping.items():
                        if month in months_in_season and season_name not in seasons:
                            seasons.append(season_name)
    except Exception as e:
        app.logger.error(f"獲取蔬菜季節失敗: {e}")
    finally:
        if conn:
            conn.close()
    
    # 如果沒有找到季節，則回傳 "全年"
    if not seasons:
        return "全年"
    
    return ",".join(seasons)



# @app.route("/api/image/<filename>")
# def get_image(filename):
#     # ... (MinIO 函式不變)
#     s3 = boto3.client(
#         "s3",
#         endpoint_url=os.getenv("MINIO_ENDPOINT"),
#         aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
#         aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
#         config=boto3.session.Config(signature_version="s3v4"),
#     )
#     bucket = os.getenv("MINIO_BUCKET_NAME", "veg-data-bucket")
#     key = f"images/{filename}"
#     try:
#         obj = s3.get_object(Bucket=bucket, Key=key)
#         return Response(obj["Body"].read(), mimetype="image/jpeg")
#     except Exception as e:
#         app.logger.error(f"MinIO 取檔失敗: bucket={bucket} key={key} error={e}", exc_info=True)
#         return "Not found", 404

@app.route("/api/image/<image_name>", methods=["GET"])
def get_image(image_name):
    minio_client = get_minio_client()
    if minio_client is None:
        return "Internal Server Error", 500

    minio_bucket = os.getenv("MINIO_BUCKET_NAME", "veg-data-bucket")
    object_name = f"images/{image_name}"

    try:
        # 從 MinIO 獲取圖片物件
        response = minio_client.get_object(Bucket=minio_bucket, Key=object_name)
        image_data = response['Body'].read()

        # 根據圖片名稱判斷 Content-Type
        if image_name.lower().endswith(('.jpg', '.jpeg')):
            content_type = 'image/jpeg'
        elif image_name.lower().endswith('.png'):
            content_type = 'image/png'
        else:
            content_type = 'application/octet-stream'

        return Response(image_data, mimetype=content_type)
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            app.logger.error(f"Image not found in MinIO: {object_name}")
            return "Image not found", 404
        app.logger.error(f"Error getting image from MinIO: {e}")
        return "Internal Server Error", 500
    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        return "Internal Server Error", 500

# 新增 API 端點來獲取所有蔬菜清單
# ... (其他程式碼不變)
@app.route('/api/vegetables', methods=['GET'])
def get_vegetables():
    import random
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': '無法連接資料庫'}), 500

    try:
        cur = conn.cursor()
        # 取得每個蔬菜的最新價格與對應的預測價格
        sql = """
        SELECT
            bv.id,
            bv.vege_name,
            dap.avg_price_per_kg,
            dap."ObsTime" AS latest_obstime,
            pp.predict_price
        FROM
            basic_vege bv
        LEFT JOIN LATERAL (
            SELECT avg_price_per_kg, "ObsTime"
            FROM daily_avg_price
            WHERE vege_id = bv.id AND avg_price_per_kg IS NOT NULL
            ORDER BY "ObsTime" DESC
            LIMIT 1
        ) dap ON TRUE
        LEFT JOIN price_predictions pp
            ON pp.vege_id = bv.id
            AND pp.target_date = dap."ObsTime" + INTERVAL '7 day'
        ORDER BY bv.vege_name;
        """
        cur.execute(sql)
        rows = cur.fetchall()

        veg_list = []
        for veg_id, veg_name, avg_price_per_kg, latest_obstime, predict_price in rows:
            season_string = get_vegetable_seasons(veg_id)

            # 取得近 30 筆歷史價格（由舊到新）
            price_history = []
            try:
                cur_hist = conn.cursor()
                cur_hist.execute(
                    """
                    SELECT avg_price_per_kg
                    FROM daily_avg_price
                    WHERE vege_id = %s AND avg_price_per_kg IS NOT NULL
                    ORDER BY "ObsTime" DESC
                    LIMIT 30
                    """,
                    (veg_id,)
                )
                hist_rows = cur_hist.fetchall()
                # 轉為 list 並反轉為由舊到新，符合前端圖表呈現
                price_history_desc = [float(r[0]) for r in hist_rows if r[0] is not None]
                price_history = list(reversed(price_history_desc))
            except Exception as e:
                app.logger.error(f"Error fetching price history for veg_id={veg_id}: {e}")
                price_history = []

            # 當前價格
            current_price = float(avg_price_per_kg) if avg_price_per_kg is not None else None

            # 價格變動：使用預測相對於目前價格
            if current_price is not None and predict_price is not None:
                try:
                    change_pct = ((float(predict_price) - current_price) / current_price) * 100.0
                    price_change = f"{'+' if change_pct >= 0 else ''}{change_pct:.1f}%"
                except Exception:
                    price_change = "N/A"
            else:
                price_change = "N/A"

            veg_list.append({
                'id': veg_id,
                'name': veg_name,
                'description': f"新鮮{veg_name}，營養豐富，是您餐桌上的最佳選擇。",
                'season': season_string,
                'priceChange': price_change,
                'currentPrice': current_price,
                'latestObsTime': latest_obstime.isoformat() if latest_obstime else None,
                'image': f"/api/image/{veg_name}.jpg",
                'priceHistory': price_history,
                'nutrition': {
                    '熱量': random.randint(15, 50),
                    '纖維': round(random.uniform(1, 5), 1),
                    '維生素C': random.randint(10, 100),
                    '維生素A': random.randint(0, 500),
                    '鐵質': round(random.uniform(0.3, 3), 1),
                    '鈣質': random.randint(10, 150)
                }
            })

        return jsonify(veg_list)

    except Exception as e:
        app.logger.error(f"Error fetching vegetables: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            cur.close()
            conn.close()


@app.route('/api/vegetables/<int:veg_id>', methods=['GET'])
def get_vegetable_detail(veg_id):
    import random
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': '無法連接資料庫'}), 500

    try:
        cur = conn.cursor()
        # 最新價格與預測價格
        cur.execute(
            """
            SELECT
                b.id,
                b.vege_name,
                dap.avg_price_per_kg,
                dap."ObsTime" AS latest_obstime,
                pp.predict_price
            FROM basic_vege b
            LEFT JOIN LATERAL (
                SELECT avg_price_per_kg, "ObsTime"
                FROM daily_avg_price
                WHERE vege_id = b.id AND avg_price_per_kg IS NOT NULL
                ORDER BY "ObsTime" DESC
                LIMIT 1
            ) dap ON TRUE
            LEFT JOIN price_predictions pp
                ON pp.vege_id = b.id
                AND pp.target_date = dap."ObsTime" + INTERVAL '7 day'
            WHERE b.id = %s
            """,
            (veg_id,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({'error': '找不到蔬菜'}), 404

        veg_id_db, veg_name, avg_price_per_kg, latest_obstime, predict_price = row

        # 價格歷史（近 30 筆，由舊到新）
        price_history = []
        try:
            cur.execute(
                """
                SELECT avg_price_per_kg
                FROM daily_avg_price
                WHERE vege_id = %s AND avg_price_per_kg IS NOT NULL
                ORDER BY "ObsTime" DESC
                LIMIT 30
                """,
                (veg_id,)
            )
            hist_rows = cur.fetchall()
            price_history_desc = [float(r[0]) for r in hist_rows if r[0] is not None]
            price_history = list(reversed(price_history_desc))
        except Exception as e:
            app.logger.error(f"Error fetching price history for veg_id={veg_id}: {e}")
            price_history = []

        # 當前價格
        current_price = float(avg_price_per_kg) if avg_price_per_kg is not None else None
        # 價格變動
        if current_price is not None and predict_price is not None:
            try:
                change_pct = ((float(predict_price) - current_price) / current_price) * 100.0
                price_change = f"{'+' if change_pct >= 0 else ''}{change_pct:.1f}%"
            except Exception:
                price_change = "N/A"
        else:
            price_change = "N/A"

        season_string = get_vegetable_seasons(veg_id)

        vegetable = {
            'id': veg_id_db,
            'name': veg_name,
            'description': f"新鮮{veg_name}，營養豐富，是您餐桌上的最佳選擇。",
            'season': season_string,
            'priceChange': price_change,
            'currentPrice': current_price,
            'image': f"/api/image/{veg_name}.jpg",
            'imageUrl': f"/api/image/{veg_name}.jpg",
            'priceHistory': price_history,
            'nutrition': {
                '熱量': random.randint(15, 50),
                '纖維': round(random.uniform(1, 5), 1),
                '維生素C': random.randint(10, 100),
                '維生素A': random.randint(0, 500),
                '鐵質': round(random.uniform(0.3, 3), 1),
                '鈣質': random.randint(10, 150)
            }
        }
        return jsonify(vegetable)

    except Exception as e:
        app.logger.error(f"Error fetching vegetable detail: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            cur.close()
            conn.close()


@app.route('/api/price', methods=['POST'])
def get_price_by_ids():
    ids = request.json.get('ids', [])
    if not ids:
        return jsonify({'error': '請提供蔬菜id列表'}), 400
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': '無法連接資料庫'}), 500
    try:
        cur = conn.cursor()
        sql = """
        SELECT
            bv.id,
            bv.vege_name,
            dap.avg_price_per_kg,
            dap."ObsTime" AS latest_obstime,
            va.alias,
            pp.predict_price,
            pp.target_date
        FROM
            basic_vege bv
        LEFT JOIN LATERAL (
            SELECT avg_price_per_kg, "ObsTime"
            FROM daily_avg_price
            WHERE vege_id = bv.id AND avg_price_per_kg IS NOT NULL
            ORDER BY "ObsTime" DESC
            LIMIT 1
        ) dap ON TRUE
        LEFT JOIN vege_alias va
            ON va.vege_id = bv.id AND va.similarity_weight = 1
        LEFT JOIN price_predictions pp
            ON pp.vege_id = bv.id
            AND pp.target_date = dap."ObsTime" + INTERVAL '7 day'
        WHERE bv.id IN %s
        """
        cur.execute(sql, (tuple(ids),))
        rows = cur.fetchall()
        veg_dict = {}
        for row in rows:
            veg_id, vege_name, avg_price_per_kg, latest_obstime, alias, predict_price, target_date = row
            price_change = None
            if avg_price_per_kg and predict_price:
                price_change = round((predict_price - avg_price_per_kg) / avg_price_per_kg * 100, 2)
            latest_obs_str = latest_obstime.isoformat() if latest_obstime else None
            predict_target_str = target_date.isoformat() if target_date else None
            if veg_id not in veg_dict:
                veg_dict[veg_id] = {
                    'id': veg_id,
                    'name': vege_name,
                    'alias': [],
                    'currentPrice': float(avg_price_per_kg) if avg_price_per_kg else None,
                    'priceChange': price_change,
                    'latestObsTime': latest_obs_str,
                    'predictTargetDate': predict_target_str,
                    'image': f"{os.getenv('url_9000')}/veg-data-bucket/images/{vege_name}.jpg"
                }
            if alias:
                veg_dict[veg_id]['alias'].append(alias)
        veg_list = list(veg_dict.values())
        return jsonify(veg_list)
    except Exception as e:
        app.logger.error(f"Error fetching vegetables: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            cur.close()
            conn.close()


@app.route('/api/recipes/<int:veg_id>', methods=['GET'])
def get_recipes(veg_id):
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': '無法連接資料庫'}), 500

    try:
        cur = conn.cursor()
        # 修正：使用 AS 別名讓資料處理更清晰，並確保查詢所有必要欄位
        cur.execute("""
            SELECT
                mr.id AS recipe_id,
                mr.recipe AS recipe_title,
                rs.step_no,
                rs.description
            FROM main_recipe AS mr
            JOIN recipe_steps AS rs ON mr.id = rs.recipe_id
            WHERE mr.vege_id = %s
            ORDER BY mr.id, rs.step_no;
        """, (veg_id,))
        rows = cur.fetchall()

        if not rows:
            return jsonify({'message': '查無此蔬菜的食譜'}), 200 # 200 表示成功但無資料

        # 使用 defaultdict 處理資料，確保資料結構正確
        recipes_map = defaultdict(lambda: {
            'id': None,
            'title': '',
            'steps': []
        })

        for row in rows:
            # 透過 cursor.description 取得欄位名稱，更安全
            recipe_id = row[0]
            if recipes_map[recipe_id]['id'] is None:
                recipes_map[recipe_id]['id'] = row[0]
                recipes_map[recipe_id]['title'] = row[1]
            
            recipes_map[recipe_id]['steps'].append({
                'step_no': row[2],
                'description': row[3]
            })

        # 將步驟合併為一個單一的字串，並新增預設圖片網址
        recipes_list = []
        minio_bucket = os.getenv("MINIO_BUCKET_NAME", "veg-data-bucket")
        flex_image_url = os.getenv("url_9000")
        # 根據食譜 ID 產生 MinIO 圖片 URL
        for recipe_data in recipes_map.values():
            steps_text = '\n'.join([f"步驟{s['step_no']}. {s['description']}" for s in recipe_data['steps']])
            image_url = f"/api/image/{recipe_data['id']}.jpg"
            recipes_list.append({
                'id': recipe_data['id'],
                'title': recipe_data['title'],
                'instructions': steps_text,
                'imageUrl': image_url
            })
            
        return jsonify(recipes_list)

    except Exception as e:
        # 在錯誤發生時，將錯誤寫入日誌，以便追蹤
        app.logger.error(f"Error fetching recipes for veg_id {veg_id}: {e}")
        # 回傳 500 錯誤給前端
        return jsonify({'error': '伺服器內部錯誤'}), 500
    finally:
        if conn:
            conn.close()



def get_current_season():
    month = datetime.datetime.now().month
    if 3 <= month <= 5:
        return "spring"
    elif 6 <= month <= 8:
        return "summer"
    elif 9 <= month <= 11:
        return "autumn"
    else:
        return "winter"



def get_seasonal_vegetables():
    """查詢當季最便宜的前三種蔬菜"""
    conn = get_db_connection()
    if not conn:
        app.logger.error("無法建立資料庫連線")
        return []

    seasonal_veges = []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        current_month = datetime.datetime.now().month
        month_column = f"fresh_month_{current_month:02d}"
        app.logger.info(f"正在查詢月份欄位: {month_column}")

        # === 修改後的 SQL 查詢 START ===
        # 修正1: JOIN 的資料表改為 daily_avg_price
        # 修正2: JOIN 的條件改為 b.id = p.vege_id
        # 修正3: 使用子查詢，透過 DISTINCT ON 和 ORDER BY ObsTime DESC 取得每種蔬菜最新的一筆價格
        query = f"""
            SELECT
                b.id,
                b.vege_name,
                a.alias,
                p.avg_price_per_kg
            FROM
                basic_vege AS b
            LEFT JOIN
                vege_alias AS a ON b.id = a.vege_id AND a.similarity_weight = 1
            LEFT JOIN (
                SELECT DISTINCT ON (vege_id)
                    vege_id,
                    avg_price_per_kg
                FROM
                    daily_avg_price
                ORDER BY
                    vege_id, "ObsTime" DESC
            ) AS p ON b.id = p.vege_id
            WHERE
                b.{month_column} = 1
            ORDER BY
                p.avg_price_per_kg ASC NULLS LAST, b.vege_name
            LIMIT 3;
        """
        # === 修改後的 SQL 查詢 END ===

        app.logger.info(f"執行的 SQL 查詢: {query}")
        cur.execute(query)
        results = cur.fetchall()
        
        seasonal_veges = [dict(row) for row in results]
        app.logger.info(f"從資料庫查詢到 {len(seasonal_veges)} 筆當季蔬菜。")
        
        return seasonal_veges

    except psycopg2.Error as e:
        app.logger.error(f"查詢當季蔬菜時發生資料庫錯誤: {e}")
        return []
    except Exception as e:
        app.logger.error(f"查詢當季蔬菜時發生未知錯誤: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_recipes_by_vege_id(vege_id):
    """根據 vege_id 查詢食譜及其步驟"""
    conn = get_db_connection()
    if not conn:
        return []
    
    recipes_data = []

    minio_bucket = os.getenv("MINIO_BUCKET_NAME", "veg-data-bucket")
    try:
        cur = conn.cursor()
        
        # 1. 查詢 main_recipe 資料表
        cur.execute("SELECT id, recipe FROM main_recipe WHERE vege_id::integer = %s LIMIT 5", (vege_id,))
        main_recipes = cur.fetchall()
        
        
        for recipe_id, recipe_name in main_recipes:
            # 2. 針對每個食譜，查詢 recipe_steps
            cur.execute("SELECT description FROM recipe_steps WHERE recipe_id = %s ORDER BY step_no ASC", (recipe_id,))
            all_steps = cur.fetchall()
            
            flex_image_url = os.getenv("url_9000")
            # 根據食譜 ID 產生 MinIO 圖片 URL
            image_url = f"{flex_image_url}/{minio_bucket}/images/{recipe_id}.jpg"

            steps_list = [step[0] for step in all_steps]
            
            recipe_description = steps_list[0] if steps_list else ""
            
            recipes_data.append({
                "id": recipe_id,
                "name": recipe_name,
                "description": recipe_description,
                "image_url": image_url, # 使用預設圖片網址
                "steps": steps_list
            })
            
    except (Exception, psycopg2.DatabaseError) as error:
        app.logger.error(f"Database query failed: {error}")
        return []
    finally:
        if conn:
            cur.close()
            conn.close()
            
    return recipes_data


# 新的單一食譜 API
@app.route('/api/recipe/<int:recipe_id>', methods=['GET'])
def get_recipe_detail(recipe_id):
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': '無法連接資料庫'}), 500

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                mr.id AS recipe_id,
                mr.recipe AS recipe_title,
                rs.step_no,
                rs.description
            FROM main_recipe AS mr
            JOIN recipe_steps AS rs ON mr.id = rs.recipe_id
            WHERE mr.id::integer = %s
            ORDER BY rs.step_no;
        """, (recipe_id,))
        rows = cur.fetchall()

        if not rows:
            return jsonify({'error': '找不到該食譜'}), 404

        steps_text = '\n'.join([f"步驟{r[2]}. {r[3]}" for r in rows])
        minio_bucket = os.getenv("MINIO_BUCKET_NAME", "veg-data-bucket")
        flex_image_url = os.getenv("url_9000")
        # 根據食譜 ID 產生 MinIO 圖片 URL
        image_url = f"{flex_image_url}/{minio_bucket}/images/{recipe_id}.jpg"
        recipe = {
            'id': rows[0][0],
            'title': rows[0][1],
            'instructions': steps_text,
            'imageUrl': image_url
        }
        return jsonify(recipe)

    except Exception as e:
        app.logger.error(f"Error fetching recipe detail: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


def create_seasonal_flex_message(seasonal_veges):
    """根據當季蔬菜資料建立 Flex Carousel"""
    import urllib.parse
    if not seasonal_veges:
        return None
        

    bubbles = []
    for veg in seasonal_veges:
        veg_name = veg["vege_name"]
        alias_text = f"別名：{veg['alias']}" if veg["alias"] else "無主要別名"
        
        # 處理價格顯示，如果沒有價格資訊則顯示提示文字
        if veg["avg_price_per_kg"] is not None:
            price_text = f"目前平均售價：{veg['avg_price_per_kg']:.1f} 元/公斤"
        else:
            price_text = "目前暫無平均報價"

        # 圖片 URL
        flex_image_url = os.getenv("url_9000")
        image_filename = urllib.parse.quote(f"{veg_name}.jpg")
        image_url = f"{flex_image_url}/veg-data-bucket/images/{image_filename}"
        
        # Postback data
        encoded_veg_name = urllib.parse.quote(veg_name)
        postback_data = f"action=show_more_options&veg_id={veg['id']}&veg_name={encoded_veg_name}"

        bubble = FlexBubble(
            direction="ltr",
            hero=FlexImage(
                url=image_url,
                size="full",
                aspect_ratio="1.5:1",
                aspect_mode="cover",
                action=URIAction(uri=image_url, label="查看圖片"),
            ),
            body=FlexBox(
                layout="vertical",
                contents=[
                    FlexText(text=veg_name, weight="bold", size="xl"),
                    FlexText(text=alias_text, size="sm", color="#aaaaaa", margin="md"),
                    FlexText(text=price_text, size="sm", color="#555555", margin="md"),
                ],
            ),
            footer=FlexBox(
                layout="vertical",
                spacing="sm",
                contents=[
                    FlexButton(
                        style="primary",
                        height="sm",
                        color="#00B900",
                        action=PostbackAction(
                            label=f"我想了解 {veg_name} 更多！",
                            data=postback_data,
                            displayText=f"我想了解關於「{veg_name}」的更多資訊！",
                        ),
                    ),
                ],
            ),
        )
        bubbles.append(bubble)

    return FlexMessage(
        alt_text="當季蔬菜推薦",
        contents=FlexCarousel(contents=bubbles)
    )


def create_recipe_flex_carousel(recipes_data):
    """根據食譜資料建立 Flex Carousel"""
    if not recipes_data:
        return None
        
    bubbles = []
    for recipe in recipes_data:
        steps_text = "步驟：\n" + "\n".join(
            [f"{i+1}. {step}" for i, step in enumerate(recipe["steps"])]
        )
        
        bubble_body_contents = [
            FlexText(text=recipe["name"], weight="bold", size="xl", wrap=True),
            FlexText(text=recipe["description"], size="sm", color="#aaaaaa", wrap=True, margin="sm"),
            FlexText(text=steps_text, size="sm", color="#555555", wrap=True, margin="md"),
        ]
        
        web_url = os.getenv("url_5000")
        
        bubble = FlexBubble(
            direction="ltr",
            hero=FlexImage(
                url=recipe["image_url"],
                size="full",
                aspect_ratio="1.5:1",
                aspect_mode="cover",
                action=URIAction(uri=recipe["image_url"], label="查看圖片"),
            ),
            body=FlexBox(layout="vertical", contents=bubble_body_contents),
            footer=FlexBox(
                layout="vertical",
                spacing="sm",
                contents=[
                    FlexButton(
                        style="link",
                        height="sm",
                        action=URIAction(
                            label="前往網站看得更詳細", uri=f"{web_url}/?section=recipe&id={recipe['id']}"
                        ),
                    ),
                ],
            ),
        )
        bubbles.append(bubble)
        
    return FlexMessage(
        alt_text="相關食譜",
        contents=FlexCarousel(contents=bubbles)
    )


def _create_vegetable_flex_message(
    veg_data_list, alt_text_prefix, is_nutrient_search=False, confidence=None
):
    bubbles = []
    for veg_data in veg_data_list:
        aliases_text = (
            "別名：" + ", ".join(veg_data["aliases"])
            if veg_data["aliases"]
            else "無別名"
        )
        all_nutrients_detail = []
        for i, (nutrient_key, nutrient_value) in enumerate(
            veg_data["all_nutrients"].items()
        ):
            if i < 2:
                continue
            if i >= 7:
                break
            display_name = NUTRIENT_DISPLAY_MAPPING.get(nutrient_key, "")
            if not display_name:
                display_name = nutrient_key.split("_")[0].capitalize()

            current_unit_abbreviation = (
                nutrient_key.split("_")[-1] if "_" in nutrient_key else ""
            )
            current_unit = UNIT_ABBREVIATION_TO_CHINESE.get(
                current_unit_abbreviation, ""
            )

            if pd.isna(nutrient_value):
                nutrient_value_display = "N/A"
            else:
                nutrient_value_display = (
                    f"{nutrient_value:.1f}"
                    if isinstance(nutrient_value, (int, float))
                    else str(nutrient_value)
                )
            all_nutrients_detail.append(
                f"{display_name}：{nutrient_value_display}{current_unit}"
            )

        all_nutrients_text = "營養資訊(每100 克可食部分)：\n" + "\n".join(
            all_nutrients_detail
        )
        bubble_body_contents = [
            FlexText(text=veg_data["chinese_name"], weight="bold", size="xl"),
            FlexText(
                text=aliases_text, size="sm", color="#aaaaaa", wrap=True, margin="sm"
            ),
            # FlexText(
            #     text=all_nutrients_text,
            #     size="sm",
            #     color="#555555",
            #     wrap=True,
            #     margin="md",
            # ),
        ]
        if (
            is_nutrient_search
            and "nutrient_name" in veg_data
            and "nutrient_value" in veg_data
            and "unit" in veg_data
        ):
            bubble_body_contents.insert(
                1,
                FlexText(
                    text=f"查詢成分：{veg_data['nutrient_name']} {veg_data['nutrient_value']}{veg_data['unit']}",
                    size="md",
                    margin="md",
                ),
            )
        # ⭐ 新增：如果提供了信心度，就將其加入卡片內容
        if confidence is not None:
            bubble_body_contents.insert(
                1, # 插在菜名後面
                FlexText(
                    text=f"預測信心指數：{confidence*100:.1f}%",
                    size="md",
                    color="#1E90FF", # 使用不同顏色突顯
                    weight="bold",
                    margin="md"
                )
            )

        # 加入營養資訊
        bubble_body_contents.append(FlexText(
            text=all_nutrients_text,
            size="sm",
            color="#555555",
            wrap=True,
            margin="md",
        ))

        import urllib.parse
        flex_image_url = os.getenv("url_9000")
        web_url = os.getenv("url_5000")
        veg_name = veg_data["chinese_name"]
        image_filename = urllib.parse.quote(f"{veg_name}.jpg")
        image_url = f"{flex_image_url}/veg-data-bucket/images/{image_filename}"

        footer_buttons = []
        if not is_nutrient_search: # 辨識圖片的結果
            encoded_veg_name = urllib.parse.quote(veg_data['chinese_name'])
            # 按鈕 1: 我想了解這個更多！
            footer_buttons.append(
                FlexButton(
                    style="primary",
                    height="sm",
                    color="#00B900",
                    action=PostbackAction(
                        label="我想了解這個更多！",
                        data=f"action=show_more_options&veg_id={veg_data['id']}&veg_name={encoded_veg_name}",
                        displayText=f"我想了解關於「{veg_data['chinese_name']}」的更多資訊！"
                    ),
                )
            )
            # 按鈕 2: 看起來不太像…
            footer_buttons.append(
                FlexButton(
                    style="secondary",
                    height="sm",
                    action=PostbackAction(
                        label="看起來不太像…",
                        data="action=recognize_again",
                        displayText="嗯...這個辨識結果好像不太對"
                    ),
                )
            )
        # 營養查詢或文字搜尋的結果
        else:
            encoded_veg_name = urllib.parse.quote(veg_data['chinese_name'])
            # 只顯示「我想了解這個更多！」按鈕
            footer_buttons.append(
                FlexButton(
                    style="primary",
                    height="sm",
                    color="#00B900",
                    action=PostbackAction(
                        label="我想了解這個更多！",
                        data=f"action=show_more_options&veg_id={veg_data['id']}&veg_name={encoded_veg_name}",
                        displayText=f"我想了解關於「{veg_data['chinese_name']}」的更多資訊！"
                    ),
                )
            )

        bubble = FlexBubble(
            direction="ltr",
            hero=FlexImage(
                url=image_url,
                size="full",
                aspect_ratio="1.5:1",
                aspect_mode="cover",
                action=URIAction(uri=image_url, label="查看圖片"),
            ),
            body=FlexBox(layout="vertical", contents=bubble_body_contents),
            footer=FlexBox(
                layout="vertical",
                spacing="sm",
                contents=footer_buttons,
            ),
        )
        bubbles.append(bubble)
    if not bubbles:
        return TextMessage(
            text="沒有找到符合條件的蔬菜。"
        )
    else:
        return FlexMessage(
            alt_text=f"{alt_text_prefix}相關蔬菜",
            contents=FlexCarousel(contents=bubbles),
        )

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError(
        "LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not set in environment variables."
    )
app.logger.info(
    f"LINE_CHANNEL_ACCESS_TOKEN loaded (length: {len(LINE_CHANNEL_ACCESS_TOKEN)})"
)
app.logger.info(f"LINE_CHANNEL_SECRET loaded (length: {len(LINE_CHANNEL_SECRET)})")
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    app.logger.info("Request signature: " + signature)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Request body: " + body)
        abort(400)
    except Exception as e:
        import traceback
        app.logger.error(f"Unhandled exception in callback: {e}")
        app.logger.error(traceback.format_exc())
        abort(500)
    return "OK"

# 新增 PostbackEvent 處理
@handler.add(PostbackEvent)
def handle_postback(event):
    # 使用 urllib.parse.parse_qs 來安全地解析 postback data
    import urllib.parse
    data = event.postback.data
    app.logger.info(f"Received postback data: {data}")
    params = urllib.parse.parse_qs(data)
    action = params.get('action', [None])[0]
    
    # 檢查是否為食譜查詢
    if action == "get_recipes":
        try:
            veg_id = params.get('veg_id', [None])[0]
            if veg_id:
                veg_id = int(veg_id)
            else:
                raise ValueError("Missing veg_id in postback data")
            # 查詢食譜
            recipes = get_recipes_by_vege_id(veg_id)
            
            # 建立回覆訊息
            if recipes:
                # ⭐ 建立 Image Carousel 訊息 ⭐
                image_carousel_columns = []
                web_url = os.getenv("url_5000", "http://localhost:5000")
                for recipe in recipes:
                    image_carousel_columns.append(
                        ImageCarouselColumn(
                            image_url=recipe["image_url"],
                            action=URIAction(
                                label=recipe["name"],
                                uri=f"{web_url}/?section=recipe&id={recipe['id']}"
                            )
                        )
                    )

                image_carousel_message = TemplateMessage(
                    alt_text="相關食譜",
                    template=ImageCarouselTemplate(
                        columns=image_carousel_columns
                    )
                )

                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[image_carousel_message]
                    )
                )
            else:
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="找不到相關食譜喔！")]
                    )
                )
        except Exception as e:
            app.logger.error(f"Error handling get_recipes postback: {e}")
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="處理請求時發生錯誤，請稍後再試。")]
                )
            )
    elif action == "show_more_options":
        try:
            veg_id = params.get('veg_id', [None])[0]
            # 解碼蔬菜名稱
            encoded_veg_name = params.get('veg_name', [None])[0]
            veg_name = urllib.parse.unquote(encoded_veg_name)
            
            if not veg_id or not veg_name:
                raise ValueError("Missing veg_id or veg_name in postback")

            web_url = os.getenv("url_5000", "http://localhost:5000")

            # 建立帶有快速回覆按鈕的訊息
            reply_message = TextMessage(
                text=f"您想了解「{veg_name}」的什麼資訊呢？",
                quick_reply=QuickReply(
                    items=[
                        QuickReplyItem(action=PostbackAction(
                            label="相關食譜",
                            data=f"action=get_recipes&veg_id={veg_id}",
                            displayText=f"查詢「{veg_name}」的食譜"
                        )),
                        # 暫時用文字訊息代替，未來可擴充為價格查詢 postback
                        QuickReplyItem(action=PostbackAction(
                            label="近期價格",
                            data=f"action=get_recent_price&veg_id={veg_id}&veg_name={encoded_veg_name}",
                            displayText=f"我想知道「{veg_name}」的價格"
                        )),
                        QuickReplyItem(action=URIAction(
                            label="詳細營養資訊",
                            uri=f"{web_url}/?section=detail&id={veg_id}"
                        )),
                    ]
                )
            )
            
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply_message]
                )
            )

        except Exception as e:
            app.logger.error(f"Error handling show_more_options postback: {e}")
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="處理請求時發生錯誤，請稍後再試。")]
                )
            )
    
    # ⭐ 新增：處理近期價格查詢
    elif action == "get_recent_price":
        try:
            veg_id_str = params.get('veg_id', [None])[0]
            if not veg_id_str:
                raise ValueError("Missing veg_id in postback data")
            veg_id = int(veg_id_str)

            price_info = get_recent_price_info(veg_id)
            if not price_info:
                raise ValueError("找不到價格資訊或資料不足")

            flex_message = create_price_flex_message(price_info)
            messages = [TextMessage(text="菜菜子找到了相關的蔬菜價格資訊給你！")]
            if flex_message:
                messages.append(flex_message)

            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=messages
                )
            )
        except Exception as e:
            app.logger.error(f"Error handling get_recent_price postback: {e}")
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="抱歉，目前無法取得價格資訊。請稍後再試。")]
                )
            )
    # ⭐ 新增：處理「看起來不太像…」的 postback
    elif action == "recognize_again":
        reply_message = TextMessage(
            text="可以從其他角度再拍一張給菜菜子看嗎？",
            quick_reply=QuickReply(
                items=[
                    QuickReplyItem(action=CameraAction(label="重新拍攝")),
                    QuickReplyItem(action=CameraRollAction(label="重新上傳")),
                ]
            )
        )
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[reply_message]
            )
        )


@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    app.logger.info("進入 handle_image_message 函數 ")
    image_filename = f"temp_image_{uuid.uuid4()}.jpg"
    try:
        # ... (下載圖片和辨識的程式碼不變)
        headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
        url = f"https://api-data.line.me/v2/bot/message/{event.message.id}/content"
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code != 200:
            raise Exception(f"圖片下載失敗，狀態碼：{response.status_code}")
        with open(image_filename, "wb") as f:
            for chunk in response.iter_content():
                f.write(chunk)
        with open(image_filename, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        recognition_result = rec_veg(encoded_string)
        veg_name = "未知蔬菜"
        confidence = 0.0
        try:
            if isinstance(recognition_result, dict):
                veg_name = recognition_result.get("prediction", veg_name)
                conf_value = recognition_result.get("confidence", "")
                if isinstance(conf_value, str):
                    conf_value = conf_value.replace("%", "").strip()
                    if conf_value:
                        confidence = float(conf_value) / 100.0
                elif isinstance(conf_value, (int, float)):
                    confidence = conf_value / 100.0 if conf_value > 1 else float(conf_value)
            elif isinstance(recognition_result, str):
                lines = recognition_result.split("\n")
                if len(lines) >= 2:
                    if "預測類別：" in lines[0]:
                        veg_name = lines[0].replace("預測類別：", "").strip()
                    if "信心度：" in lines[1]:
                        confidence_str = (
                            lines[1].replace("信心度：", "").replace("%", "").strip()
                        )
                        confidence = float(confidence_str) / 100.0
            else:
                veg_name = "未知蔬菜"
                confidence = 0.0
        except Exception as e:
            app.logger.error(f"解析 recognition_result 失敗: {e}")
            import traceback
            app.logger.error(traceback.format_exc())
            veg_name = "未知蔬菜"
            confidence = 0.0
        # 2. ⭐ 根據信心度決定回覆訊息
        prefix_message_text = ""
        if confidence >= 0.9:
            prefix_message_text = f"菜菜子有高度的信心！這是{veg_name}！"
        elif confidence >= 0.8:
            prefix_message_text = f"菜菜子覺得這八成是 {veg_name} 唷～"
        else: # < 0.8
            prefix_message_text = "菜菜子不太確定，可以從其他角度再拍一張給我看嗎？"

        # 3. 準備要發送的訊息列表
        messages_to_reply = [TextMessage(text=prefix_message_text)]

        # 4. 如果信心度 >= 80%，則準備並附加 Flex Message 卡片
        if confidence >= 0.8:
            vegetable_details = get_vegetables_by_name_or_alias(veg_name)
            
            if vegetable_details and isinstance(vegetable_details, list):
                # 呼叫我們修改過的函式，傳入信心度
                flex_message = _create_vegetable_flex_message(
                    vegetable_details, 
                    f"辨識結果：{veg_name}",
                    confidence=confidence
                )
                if flex_message:
                    messages_to_reply.append(flex_message)
            else:
                # 即使辨識出來，也可能資料庫裡沒有，做個保護
                messages_to_reply.append(TextMessage(text=f"雖然辨識出是「{veg_name}」，但在我的資料庫裡找不到它的詳細資料耶！"))

        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token, messages=messages_to_reply
            )
        )
        app.logger.info("Image recognition reply sent successfully.")
    except Exception as e:
        import traceback
        app.logger.info(traceback.format_exc())
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TextMessage(text=f"圖片處理失敗：{e}")
                ],
            )
        )
    finally:
        if os.path.exists(image_filename):
            os.remove(image_filename)

def resolve_veg_name_to_id_and_name(name_query):
    """使用名稱或別名解析到第一個匹配的蔬菜 id 與標準名稱"""
    try:
        candidates = get_vegetables_by_name_or_alias(name_query)
        if not candidates:
            return None
        # 優先精準比對中文名或別名
        normalized = str(name_query).strip()
        for c in candidates:
            cname = c.get('chinese_name') or c.get('vege_name')
            aliases = c.get('aliases') or c.get('alias') or []
            if cname == normalized or normalized in aliases:
                vid = c.get('id') or c.get('vege_id')
                return (int(vid), cname)
        # 否則取第一筆
        first = candidates[0]
        vid = first.get('id') or first.get('vege_id')
        cname = first.get('chinese_name') or first.get('vege_name')
        return (int(vid), cname)
    except Exception as e:
        app.logger.error(f"resolve_veg_name_to_id_and_name failed for '{name_query}': {e}")
        return None


def get_current_price_by_name(name_query):
    """以名稱或別名查詢目前價格（回傳 price_info 與標準名稱）"""
    resolved = resolve_veg_name_to_id_and_name(name_query)
    if not resolved:
        return None, None
    veg_id, cname = resolved
    price_info = get_recent_price_info(veg_id)
    return price_info, cname


# app.py

def try_handle_price_text_query(text):
    """針對文字輸入嘗試處理價格相關查詢，並回傳包含文字與 Flex 字卡的訊息列表"""
    try:
        raw = text.replace('？', '?').replace('！', '!').strip()
        msgs = []
        
        # 模式1：A、B、C 哪個便宜 (多者比較)
        if raw.endswith("哪個便宜") or raw.endswith("哪個比較便宜"):
            items_part = raw.replace("哪個比較便宜", "").replace("哪個便宜", "").strip()
            names = [s.strip() for s in re.split(r"[、,，\s]+", items_part) if s.strip()]
            
            if len(names) >= 2:
                price_infos = []
                for n in names:
                    info, _ = get_current_price_by_name(n)
                    if info and info.get('current_price') is not None:
                        price_infos.append(info)
                
                if price_infos:
                    price_infos.sort(key=lambda x: x['current_price'])
                    cheapest_name = price_infos[0]['name']
                    cheapest_price = price_infos[0]['current_price']
                    
                    detail = "、".join([f"{info['name']} ${info['current_price']:.1f}" for info in price_infos])
                    summary_text = f"幫您比較了一下，目前是 {cheapest_name} 最便宜喔！\n\n各項價格(元/公斤)：\n{detail}"
                    msgs.append(TextMessage(text=summary_text))
                    
                    flex_msg = create_multi_price_flex_carousel(price_infos, alt_text="蔬菜價格比較")
                    if flex_msg:
                        msgs.append(flex_msg)
                    return msgs
                else:
                    return [TextMessage(text="沒有取得有效的價格資料，可能暫時沒有報價。")]

        # 模式2：A 有比 B 貴嗎 (兩者比較)
        m = re.search(r"^\s*(.+?)\s*有比\s*(.+?)\s*貴嗎\s*\?*$", raw)
        if m:
            a_name = m.group(1).strip()
            b_name = m.group(2).strip()
            a_info, a_std = get_current_price_by_name(a_name)
            b_info, b_std = get_current_price_by_name(b_name)
            
            if a_info and b_info and a_info.get('current_price') is not None and b_info.get('current_price') is not None:
                a_price = a_info['current_price']
                b_price = b_info['current_price']
                
                if a_price > b_price:
                    ans = f"是的，{a_std} (${a_price:.1f}) 目前比 {b_std} (${b_price:.1f}) 貴一些。"
                elif a_price < b_price:
                    ans = f"沒有喔，{a_std} (${a_price:.1f}) 目前比 {b_std} (${b_price:.1f}) 便宜。"
                else:
                    ans = f"{a_std} 和 {b_std} 的價格差不多喔！ (都是 ${a_price:.1f})"
                
                msgs.append(TextMessage(text=ans))
                flex_msg = create_multi_price_flex_carousel([a_info, b_info], alt_text=f"{a_std}與{b_std}的價格資訊")
                if flex_msg:
                    msgs.append(flex_msg)
                return msgs
            else:
                return [TextMessage(text="抱歉，無法取得完整的價格資料，請稍後再試或換個品項比較。")]

        # 模式3：單一品項查詢 (包含 '多少錢', '價格', '是什麼', 或純名稱)
        # 把所有單一品項的關鍵字判斷合併在一起
        veg_name_to_search = None
        if any(k in raw for k in ["多少錢", "賣多少", "一斤", "多少", "價格"]):
            veg_name_to_search = re.split(r"[\s,，、?？!！]+", raw)[0].strip()
        else:
            m_what = re.search(r"^\s*(.+?)\s*是什麼\s*\?*$", raw)
            if m_what:
                veg_name_to_search = m_what.group(1).strip()
            else:
                # 檢查是否為單純的蔬菜名稱
                resolved = resolve_veg_name_to_id_and_name(raw)
                if resolved:
                    veg_name_to_search = raw

        if veg_name_to_search:
            info, cname = get_current_price_by_name(veg_name_to_search)
            if info:
                msgs.append(TextMessage(text=f"菜菜子找到了「{cname}」的價格資訊給你參考！"))
                # 使用新的通用函式，傳入一個元素的列表
                flex_msg = create_multi_price_flex_carousel([info])
                if flex_msg:
                    msgs.append(flex_msg)
                return msgs
            else:
                return [TextMessage(text=f"找不到「{veg_name_to_search}」的價格資訊，可能暫時沒有報價。")]

        return None # 如果所有模式都不匹配，回傳 None
    except Exception as e:
        app.logger.error(f"try_handle_price_text_query error: {e}")
        return None

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    print(f"Received text: {event.message.text}")
    try:
        messages_to_reply = []
        text = event.message.text.strip()

        seasonal_keywords = ("當季蔬菜", "/fresh", "今天適合買什麼", "這個月有什麼蔬菜", "盛產的有什麼")

        if text == "辨識蔬菜":
            reply_message = TextMessage(
                text="請選擇拍照或從相簿選擇圖片(請盡量讓背景單純)：",
                quick_reply=QuickReply(
                    items=[
                        QuickReplyItem(action=CameraAction(label="開啟相機")),
                        QuickReplyItem(action=CameraRollAction(label="從相簿選擇")),
                    ]
                ),
            )
            messages_to_reply.append(reply_message)
        elif text == "食譜推薦":
            reply_message = TextMessage(
                text="請輸入您想用甚麼食材，來份佳餚呢"
            )
            messages_to_reply.append(reply_message)
        elif text in seasonal_keywords:
            app.logger.info(f"Keyword matched for seasonal vegetables: {text}")
            seasonal_veges = get_seasonal_vegetables()
            
            if seasonal_veges:
                # 訊息 1: 引導文字
                messages_to_reply.append(TextMessage(text="菜菜子幫你找了一些當季便宜的好選擇！"))
                
                # 訊息 2: Flex Message 卡片
                flex_message = create_seasonal_flex_message(seasonal_veges)
                app.logger.info(f"Flex message created: {flex_message}")
                if flex_message:
                    app.logger.info(f"Flex message contents: {flex_message.contents}")
                messages_to_reply.append(flex_message)



                web_url = os.getenv("url_5000", "http://localhost:5000")
                season = get_current_season()
                seasonal_url = f"{web_url}/?section=overview&season={season}"

                # 訊息 3: 查看完整清單的按鈕
                see_more_message = TextMessage(
                    text="想知道菜菜子知道的所有當季蔬菜嗎？",
                    quick_reply=QuickReply(items=[
                        QuickReplyItem(action=URIAction(
                            label="查看當季蔬菜清單",
                            uri=seasonal_url # 依照你的規劃指向 web/fresh
                        ))
                    ])
                )
                messages_to_reply.append(see_more_message)

            else:
                messages_to_reply.append(TextMessage(text="哎呀，菜菜子目前找不到符合條件的當季蔬菜資訊耶！"))
            
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=messages_to_reply
                )
            )
        else:
            # 優先嘗試價格相關文字查詢
            price_msgs = try_handle_price_text_query(text)
            if price_msgs:
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=price_msgs
                    )
                )
                return

            nutrient_input = text
            print(f"DEBUG: Processing nutrient input: '{nutrient_input}'")

            # 這裡的調用已移除 MinIO 檔案名稱參數
            recommendation_result = get_top_vegetables_by_nutrient(nutrient_input)
            print(f"DEBUG: Recommendation result for '{nutrient_input}': {recommendation_result}")
            
            reply_messages = [] # 使用一個列表來收集所有要回覆的訊息
            
            # 檢查營養素搜尋結果
            if recommendation_result and isinstance(recommendation_result, list) and len(recommendation_result) > 0:
                valid_vegetables = []
                for veg in recommendation_result:
                    if veg and (veg.get('id') or veg.get('vege_id')) and veg.get('chinese_name') and veg.get('all_nutrients'):
                        temp_veg = veg.copy()
                        if 'vege_id' in temp_veg:
                            temp_veg['id'] = temp_veg['vege_id']
                        valid_vegetables.append(temp_veg)
                
                if valid_vegetables:
                    # 檢查是否為複合查詢（包含蔬菜名稱和營養素）
                    nutrient_keywords = ["蛋白質", "脂肪", "碳水化合物", "纖維", "維生素", "礦物質", "鈣", "鐵", "鋅", "鉀", "鈉", "鎂", "磷", "葉酸", "熱量", "糖", "水", "營養", "成分", "含量"]
                    contains_nutrient = any(keyword in nutrient_input for keyword in nutrient_keywords)
                    
                    if contains_nutrient and len(valid_vegetables) == 1:
                        # 複合查詢：顯示單一蔬菜的營養資訊卡片
                        single_flex_message = _create_vegetable_flex_message(
                            valid_vegetables,
                            f"「{valid_vegetables[0]['chinese_name']}」的營養資訊",
                            is_nutrient_search=True,
                        )
                        if single_flex_message:
                            reply_messages.append(single_flex_message)
                    else:
                        # 一般營養素查詢：顯示多個蔬菜的營養資訊
                        nutrient_names = sorted(list(set(veg['nutrient_name'] for veg in valid_vegetables if 'nutrient_name' in veg)))
                        
                        # _create_grouped_nutrient_flex_message 現在會回傳一個訊息列表
                        grouped_messages = _create_grouped_nutrient_flex_message(
                            valid_vegetables,
                            f"為您推薦 {nutrient_input} 含量最高的蔬菜"
                        )

                        if grouped_messages:
                            # 如果有多個營養素，加入引導文字
                            if len(nutrient_names) > 1:
                                intro_text = f"菜菜子分別為您查詢了「{', '.join(nutrient_names)}」的結果："
                                reply_messages.append(TextMessage(text=intro_text))
                            
                            # 將所有獨立的 FlexMessage 加入待回覆列表
                            reply_messages.extend(grouped_messages)

            # 如果營養素搜尋沒有結果，檢查是否為錯誤訊息
            if not reply_messages:
                if isinstance(recommendation_result, str) and "錯誤" in recommendation_result:
                    # 營養素搜尋失敗，給出明確的錯誤訊息
                    reply_messages.append(TextMessage(text=f"營養素搜尋失敗：{recommendation_result}"))
                else:
                    # 如果沒有營養素結果，才嘗試用蔬菜名稱搜尋
                    vegetable_search_result = get_vegetables_by_name_or_alias(nutrient_input)
                    print(f"DEBUG: Vegetable search result for '{nutrient_input}': {vegetable_search_result}")

                    if vegetable_search_result and isinstance(vegetable_search_result, list):
                        # ... (這部分的邏輯和原先類似，但確保結果被加到 reply_messages 列表中)
                        limited_vegetable_search_result = vegetable_search_result[:12]
                        valid_vegetables = []
                        for veg in limited_vegetable_search_result:
                            if veg and (veg.get('id') or veg.get('vege_id')) and veg.get('chinese_name') and veg.get('all_nutrients'):
                                temp_veg = veg.copy()
                                if 'vege_id' in temp_veg:
                                    temp_veg['id'] = temp_veg['vege_id']
                                valid_vegetables.append(temp_veg)

                        if valid_vegetables:
                            single_flex_message = _create_vegetable_flex_message(
                                valid_vegetables,
                                f"為您推薦 {nutrient_input} 相關蔬菜",
                                is_nutrient_search=True,
                            )
                            if single_flex_message:
                                reply_messages.append(single_flex_message)

            # 最後，根據 reply_messages 的內容來決定如何回覆
            if not reply_messages:
                reply_messages.append(TextMessage(text="沒有找到符合條件的營養成分或蔬菜。請檢查您的輸入。"))

            # 發送回覆
            messaging_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=reply_messages)
            )
            print("Reply sent successfully.")
            return 

    except Exception as e:
        print(f"Failed to reply: {e}")



@app.route("/api/csv/<filename>")
def get_csv(filename):
    # ... (MinIO 函式不變)
    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT"),
        aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
        config=boto3.session.Config(signature_version="s3v4"),
    )
    bucket = os.getenv("MINIO_BUCKET_NAME", "veg-data-bucket")
    key = filename
    app.logger.info(f"嘗試從 MinIO 取得 bucket={bucket} key={key}")
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        return Response(obj["Body"].read(), mimetype="text/csv")
    except Exception as e:
        print(f"MinIO 取檔失敗: {e}")
        app.logger.error(f"MinIO 取檔失敗: {e}")
        return "Not found", 404

# 已改用 rec_veg_new.rec_veg，移除舊模型初始化
predictor = None

@app.route("/predict", methods=["POST"])
def handle_prediction():
    try:
        data = request.get_json()
        if not data or "image" not in data:
            return jsonify({"error": "請求格式錯誤，未包含 'image' 欄位"}), 400
        base64_image = data["image"]
        prediction_result = rec_veg(base64_image)
        if not prediction_result:
            return jsonify({"error": "辨識失敗"}), 500
        if isinstance(prediction_result, dict):
            return jsonify(prediction_result)
        else:
            return jsonify({"result": prediction_result})
    except Exception as e:
        print(f"API 處理時發生錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤，無法辨識圖片"}), 500


# app.py

def _create_price_bubble(price_info):
    """
    (內部輔助函式) 根據單一蔬菜的價格資訊，建立一個 FlexBubble。
    這段程式碼是從舊的 create_price_flex_message 抽離出來的核心。
    """
    import urllib.parse
    if not price_info:
        return None

    veg_id = price_info.get('id')
    veg_name = price_info.get('name')
    aliases = price_info.get('aliases', [])
    current_price = price_info.get('current_price')
    change_pct = price_info.get('predicted_change_pct')
    trend = price_info.get('price_trend')

    alias_text = f"別名：{', '.join(aliases)}" if aliases else "無主要別名"
    if current_price is not None:
        price_text = f"目前平均售價：{current_price:.1f} 元/公斤"
    else:
        price_text = "目前暫無平均報價"

    if trend and change_pct is not None:
        pred_text = f"未來一週漲跌預測：{trend} {'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
    else:
        pred_text = "未來一週漲跌預測：暫無預測資料"

    flex_image_url = os.getenv("url_9000")
    image_filename = urllib.parse.quote(f"{veg_name}.jpg")
    image_url = f"{flex_image_url}/veg-data-bucket/images/{image_filename}"
    encoded_veg_name = urllib.parse.quote(veg_name)

    return FlexBubble(
        direction="ltr",
        hero=FlexImage(
            url=image_url, size="full", aspect_ratio="1.5:1", aspect_mode="cover",
            action=URIAction(uri=image_url, label="查看圖片"),
        ),
        body=FlexBox(
            layout="vertical",
            contents=[
                FlexText(text=veg_name, weight="bold", size="xl", wrap=True),
                FlexText(text=alias_text, size="sm", color="#aaaaaa", wrap=True, margin="md"),
                FlexText(text=price_text, size="sm", color="#555555", wrap=True, margin="md"),
                FlexText(text=pred_text, size="sm", color="#555555", wrap=True, margin="sm"),
            ],
        ),
        footer=FlexBox(
            layout="vertical", spacing="sm",
            contents=[
                FlexButton(
                    style="primary", height="sm", color="#00B900",
                    action=PostbackAction(
                        label=f"我想了解 {veg_name} 更多！",
                        data=f"action=show_more_options&veg_id={veg_id}&veg_name={encoded_veg_name}",
                        displayText=f"我想了解關於「{veg_name}」的更多資訊！",
                    ),
                ),
                # <<< 在這裡將按鈕加回來 >>>
                FlexButton(
                    style="link",
                    height="sm",
                    action=MessageAction(
                        label="其他當季蔬菜推薦",
                        text="當季蔬菜",
                    ),
                ),
            ],
        ),
    )

def create_multi_price_flex_carousel(price_info_list, alt_text="蔬菜價格資訊"):
    """
    根據一個包含多個蔬菜價格資訊的列表，建立一個 Flex Carousel 訊息。
    """
    if not price_info_list:
        return None

    bubbles = []
    for info in price_info_list:
        bubble = _create_price_bubble(info)
        if bubble:
            bubbles.append(bubble)
    
    if not bubbles:
        return None

    return FlexMessage(
        alt_text=alt_text,
        contents=FlexCarousel(contents=bubbles)
    )


def get_recent_price_info(veg_id):
	"""查詢指定蔬菜的近期價格與預測資訊"""
	conn = get_db_connection()
	if conn is None:
		return None
	try:
		cur = conn.cursor()
		# 菜名
		cur.execute("SELECT vege_name FROM basic_vege WHERE id = %s", (veg_id,))
		row = cur.fetchone()
		if not row:
			return None
		vege_name = row[0]

		# 主要別名（similarity_weight = 1）
		cur.execute(
			"""
			SELECT alias
			FROM vege_alias
			WHERE vege_id = %s AND similarity_weight = 1
			""",
			(veg_id,)
		)
		alias_rows = cur.fetchall()
		aliases = [r[0] for r in alias_rows if r and r[0]]

		# 最近兩筆價格（最新與昨日）
		cur.execute(
			"""
			SELECT avg_price_per_kg, "ObsTime"
			FROM daily_avg_price
			WHERE vege_id = %s AND avg_price_per_kg IS NOT NULL
			ORDER BY "ObsTime" DESC
			LIMIT 2
			""",
			(veg_id,)
		)
		price_rows = cur.fetchall()
		current_price = None
		latest_obstime = None
		yesterday_price = None
		if price_rows:
			current_price = float(price_rows[0][0]) if price_rows[0][0] is not None else None
			latest_obstime = price_rows[0][1]
			if len(price_rows) > 1 and price_rows[1][0] is not None:
				yesterday_price = float(price_rows[1][0])

		# 未來第七天的預測價格
		predict_price = None
		if latest_obstime is not None:
			cur.execute(
				"""
				SELECT predict_price
				FROM price_predictions
				WHERE vege_id = %s AND target_date = %s + INTERVAL '7 day'
				LIMIT 1
				""",
				(veg_id, latest_obstime)
			)
			pred_row = cur.fetchone()
			if pred_row and pred_row[0] is not None:
				predict_price = float(pred_row[0])

		predicted_change_pct = None
		price_trend = None
		if predict_price is not None and yesterday_price is not None and yesterday_price != 0:
			predicted_change_pct = round((predict_price - yesterday_price) / yesterday_price * 100, 2)
			if predicted_change_pct > 0:
				price_trend = "上漲"
			elif predicted_change_pct < 0:
				price_trend = "下跌"
			else:
				price_trend = "持平"

		return {
			'id': veg_id,
			'name': vege_name,
			'aliases': aliases,
			'current_price': current_price,
			'predicted_change_pct': predicted_change_pct,
			'price_trend': price_trend,
		}
	except Exception as e:
		app.logger.error(f"Error fetching recent price info for veg_id={veg_id}: {e}")
		return None
	finally:
		if conn:
			cur.close()
			conn.close()

def _create_grouped_nutrient_flex_message(veg_data_list, alt_text_prefix):
    """
    為營養成分查詢創建分組的 Flex 訊息。
    現在回傳一個 FlexMessage 的列表，每個營養成分一個。
    """
    if not veg_data_list:
        return None

    # 按營養成分名稱分組
    grouped_by_nutrient = {}
    for veg_data in veg_data_list:
        nutrient_name = veg_data.get('nutrient_name', '未知營養成分')
        if nutrient_name not in grouped_by_nutrient:
            grouped_by_nutrient[nutrient_name] = []
        grouped_by_nutrient[nutrient_name].append(veg_data)

    # 如果只有一個營養成分，為了保持一致性，也回傳一個包含單一元素的列表
    if len(grouped_by_nutrient) == 1:
        single_message = _create_vegetable_flex_message(veg_data_list, alt_text_prefix, is_nutrient_search=True)
        return [single_message] if single_message else []

    # 多個營養成分：為每個營養素創建一個獨立的 FlexMessage
    all_flex_messages = []
    for nutrient_name, nutrient_veg_list in grouped_by_nutrient.items():
        # 為每個營養成分創建一個 carousel
        nutrient_carousel = _create_vegetable_flex_message(
            nutrient_veg_list,
            f"富含「{nutrient_name}」的蔬菜",
            is_nutrient_search=True
        )
        if nutrient_carousel and isinstance(nutrient_carousel, FlexMessage):
            all_flex_messages.append(nutrient_carousel)

    return all_flex_messages


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)