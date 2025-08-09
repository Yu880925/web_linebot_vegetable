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
from linebot.exceptions import InvalidSignatureError
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi
from rec_veg.rec_veg import VegetablePredictor
from nutri_rec.nutri_rec import (
    get_top_vegetables_by_nutrient,
    get_vegetables_by_name_or_alias,
)
import io
import boto3
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
    URIAction,
    PostbackAction,
)
from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks.models import (
    ImageMessageContent,
    MessageEvent,
    TextMessageContent,
)

# 新增
from linebot.v3.webhooks.models import PostbackEvent  # 匯入 PostbackEvent
import json # 新增 json 模組


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
    return send_file('index.html')

app.logger.setLevel(logging.INFO)
for handler in app.logger.handlers:
    app.logger.removeHandler(handler)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
app.logger.addHandler(handler)


app.logger.info("Attempting to import rec_veg...")
from rec_veg.rec_veg import rec_veg
app.logger.info("rec_veg imported successfully.")
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

# 新增 API 端點來獲取所有蔬菜清單
@app.route('/api/vegetables', methods=['GET'])
def get_vegetables():
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': '無法連接資料庫'}), 500

    try:
        cur = conn.cursor()
        # 從 basic_vege 表格中查詢 id 和 vege_name
        cur.execute("SELECT id, vege_name FROM basic_vege ORDER BY id;")
        vegetables = cur.fetchall()

        # 將查詢結果格式化為 JSON
        veg_list = [{'id': veg[0], 'name': veg[1]} for veg in vegetables]
        return jsonify(veg_list)

    except Exception as e:
        app.logger.error(f"Error fetching vegetables: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

# ...
def get_recipes_by_vege_id(vege_id):
    """根據 vege_id 查詢食譜及其步驟"""
    conn = get_db_connection()
    if not conn:
        return []
    
    recipes_data = []
    try:
        cur = conn.cursor()
        
        # 1. 查詢 main_recipe 資料表
        cur.execute("SELECT id, recipe FROM main_recipe WHERE vege_id = %s LIMIT 10", (vege_id,))
        main_recipes = cur.fetchall()
        
        # 定義一個預設圖片網址
        default_image_url = "https://i.imgur.com/your-default-image.png"
        
        for recipe_id, recipe_name in main_recipes:
            # 2. 針對每個食譜，查詢 recipe_steps
            cur.execute("SELECT description FROM recipe_steps WHERE recipe_id = %s ORDER BY step_no ASC", (recipe_id,))
            all_steps = cur.fetchall()
            
            steps_list = [step[0] for step in all_steps]
            
            recipe_description = steps_list[0] if steps_list else ""
            
            recipes_data.append({
                "id": recipe_id,
                "name": recipe_name,
                "description": recipe_description,
                "image_url": default_image_url, # 使用預設圖片網址
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
                            label="前往網站看得更詳細", uri=f"{web_url}/?id={recipe['id']}"
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
    veg_data_list, alt_text_prefix, is_nutrient_search=False
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
            FlexText(
                text=all_nutrients_text,
                size="sm",
                color="#555555",
                wrap=True,
                margin="md",
            ),
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

        import urllib.parse
        flex_image_url = os.getenv("url_9000")
        web_url = os.getenv("url_5000")
        veg_name = veg_data["chinese_name"]
        image_filename = urllib.parse.quote(f"{veg_name}.jpg")
        image_url = f"{flex_image_url}/veg-data-bucket/images/{image_filename}"

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
        contents=[
            # 這裡加入條件判斷，只有當 veg_data 包含 'id' 時才建立按鈕
            FlexButton(
                style="link",
                height="sm",
                action=PostbackAction(
                    label="查看相關食譜",
                    data=f"action=get_recipes&veg_id={veg_data['id']}",
                    display_text="為您查詢相關食譜..."
                ),
            ) if 'id' in veg_data else None,
            FlexButton(
                style="link",
                height="sm",
                action=URIAction(
                    label="前往網站看得更詳細", uri=f"{web_url}/?id={veg_data['id']}"
                ),
            ) if 'id' in veg_data else None,
        ],
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

# ... (其餘程式碼不變)
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
    data = event.postback.data
    app.logger.info(f"Received postback data: {data}")
    
    # 檢查是否為食譜查詢
    if data.startswith("action=get_recipes"):
        # 解析 veg_id
        try:
            params = dict(param.split('=') for param in data.split('&'))
            veg_id = int(params.get('veg_id'))
        except (ValueError, KeyError):
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="食譜查詢參數錯誤。")]
                )
            )
            return

        # 查詢食譜
        recipes = get_recipes_by_vege_id(veg_id)
        
        # 建立回覆訊息
        if recipes:
            flex_message = create_recipe_flex_carousel(recipes)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[flex_message]
                )
            )
        else:
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="找不到相關食譜喔！")]
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
            lines = recognition_result.split("\n")
            if len(lines) >= 2:
                if "預測類別：" in lines[0]:
                    veg_name = lines[0].replace("預測類別：", "").strip()
                if "信心度：" in lines[1]:
                    confidence_str = (
                        lines[1].replace("信心度：", "").replace("%", "").strip()
                    )
                    confidence = float(confidence_str) / 100.0
        except Exception as e:
            app.logger.error(f"解析 recognition_result 失敗: {e}")
            import traceback
            app.logger.error(traceback.format_exc())
            veg_name = "未知蔬菜"
            confidence = 0.0
        prefix_message_text = ""
        if confidence >= 0.8:
            prefix_message_text = f'哼哼 根據我的判斷 它就是"{veg_name}"!!'
            if confidence == 1.0:
                prefix_message_text = f'真相只有一個 就是"{veg_name}"!!'
        elif confidence >= 0.5:
            prefix_message_text = f'可能是"{veg_name}"   也許讓我再看更清楚的一張'
        else:
            prefix_message_text = "歐內該  請提供更清晰的"
        if confidence >= 0.5:
            prefix_message_text += f"\n我有{confidence*100:.0f}%的信心"

        # 這裡的調用已移除 MinIO 檔案名稱參數
        vegetable_details = get_vegetables_by_name_or_alias(veg_name)
        
        messages_to_reply = [TextMessage(text=prefix_message_text)]
        if (
            confidence >= 0.5
            and vegetable_details
            and not isinstance(vegetable_details, str)
        ):
            flex_message = _create_vegetable_flex_message(
                vegetable_details, f"辨識結果：{veg_name}"
            )
            if flex_message:
                messages_to_reply.append(flex_message)
        elif confidence < 0.5:
            pass
        else:
            messages_to_reply.append(TextMessage(text="未能找到該蔬菜的詳細資訊。"))
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

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    print(f"Received text: {event.message.text}")
    try:
        reply_message = None
        text = event.message.text.strip()

        if text == "上傳圖片":
            reply_message = TextMessage(
                text="請選擇拍照或從相簿選擇圖片(請盡量讓背景單純)：",
                quick_reply=QuickReply(
                    items=[
                        QuickReplyItem(action=CameraAction(label="開啟相機")),
                        QuickReplyItem(action=CameraRollAction(label="從相簿選擇")),
                    ]
                ),
            )
        elif text == "輸入營養成分":
            reply_message = TextMessage(
                text="請輸入您想查詢的營養成分，例如：蛋白質、維生素C、鐵質\n您也可以輸入蔬菜名稱或別名，例如：高麗菜、大白菜"
            )
        else:
            nutrient_input = text
            print(f"DEBUG: Processing nutrient input: '{nutrient_input}'")

            # 這裡的調用已移除 MinIO 檔案名稱參數
            recommendation_result = get_top_vegetables_by_nutrient(nutrient_input)
            print(f"DEBUG: Recommendation result for '{nutrient_input}': {recommendation_result}")
            
            if recommendation_result and isinstance(recommendation_result, list):
                valid_vegetables = []
                for veg in recommendation_result:
                    if veg and (veg.get('id') or veg.get('vege_id')) and veg.get('chinese_name') and veg.get('all_nutrients'):
                        temp_veg = veg.copy()
                        if 'vege_id' in temp_veg:
                            temp_veg['id'] = temp_veg['vege_id']
                        valid_vegetables.append(temp_veg)
                
                if valid_vegetables:
                    reply_message = _create_vegetable_flex_message(
                        valid_vegetables,
                        f"為您推薦 {nutrient_input} 含量最高的蔬菜",
                        is_nutrient_search=True,
                    )
                else:
                    print(f"DEBUG: No valid data found for '{nutrient_input}' after filtering.")
            
            if not reply_message:
                # 這裡的調用已移除 MinIO 檔案名稱參數
                vegetable_search_result = get_vegetables_by_name_or_alias(nutrient_input)
                print(f"DEBUG: Vegetable search result for '{nutrient_input}': {vegetable_search_result}")

                if vegetable_search_result and isinstance(vegetable_search_result, list):
                    limited_vegetable_search_result = vegetable_search_result[:12]
                    valid_vegetables = []
                    for veg in limited_vegetable_search_result:
                        if veg and (veg.get('id') or veg.get('vege_id')) and veg.get('chinese_name') and veg.get('all_nutrients'):
                            temp_veg = veg.copy()
                            if 'vege_id' in temp_veg:
                                temp_veg['id'] = temp_veg['vege_id']
                            valid_vegetables.append(temp_veg)

                    if valid_vegetables:
                        reply_message = _create_vegetable_flex_message(
                            valid_vegetables,
                            f"為您推薦 {nutrient_input} 相關蔬菜",
                        )
                    else:
                        print(f"DEBUG: No valid data found for '{nutrient_input}' after filtering.")
            
            if not reply_message:
                reply_message = TextMessage(text="沒有找到符合條件的營養成分或蔬菜。請檢查您的輸入。")

        if reply_message:
            messaging_api.reply_message(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[reply_message])
            )
            print("Reply sent successfully.")

    except Exception as e:
        print(f"Failed to reply: {e}")



@app.route("/api/image/<filename>")
def get_image(filename):
    # ... (MinIO 函式不變)
    s3 = boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT"),
        aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
        config=boto3.session.Config(signature_version="s3v4"),
    )
    bucket = os.getenv("MINIO_BUCKET_NAME", "veg-data-bucket")
    key = f"images/{filename}"
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        return Response(obj["Body"].read(), mimetype="image/jpeg")
    except Exception as e:
        return "Not found", 404

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

try:
    predictor = VegetablePredictor(
        model_path="rec_veg/model_mnV2(best).keras", classes_path="rec_veg/classes.csv"
    )
except Exception as e:
    print(f"無法啟動應用程式: {e}")
    predictor = None

@app.route("/predict", methods=["POST"])
def handle_prediction():
    if not predictor:
        return jsonify({"error": "伺服器初始化失敗，模型未載入。"}), 500
    try:
        data = request.get_json()
        if not data or "image" not in data:
            return jsonify({"error": "請求格式錯誤，未包含 'image' 欄位"}), 400
        base64_image = data["image"]
        prediction_result = predictor.predict(base64_image)
        return jsonify(prediction_result)
    except Exception as e:
        print(f"API 處理時發生錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤，無法辨識圖片"}), 500


@app.route('/api/recipes/<int:veg_id>', methods=['GET'])
def get_recipes(veg_id):
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': '無法連接資料庫'}), 500

    try:
        cur = conn.cursor()
        # 使用 JOIN 語法從 main_recipe 和 recipe_steps 兩個表格中獲取資料
        # 注意：這裡的欄位名稱已經根據你提供的資訊進行了更新
        cur.execute("""
            SELECT
                mr.id,
                mr.recipe,
                mr.vege_id,
                rs.step_no,
                rs.description
            FROM main_recipe AS mr
            JOIN recipe_steps AS rs ON mr.id = rs.recipe_id
            WHERE mr.vege_id = %s
            ORDER BY mr.id, rs.step_no;
        """, (veg_id,))
        rows = cur.fetchall()

        if not rows:
            return jsonify({'message': '查無此蔬菜的食譜'}), 404

        # 將資料處理成一個適合前端使用的 JSON 格式
        recipes = defaultdict(lambda: {
            'recipe_id': None,
            'recipe_name': '',
            'vege_id': None,
            'steps': []
        })

        for row in rows:
            recipe_id = row[0]
            recipes[recipe_id]['recipe_id'] = row[0]
            recipes[recipe_id]['recipe_name'] = row[1]
            recipes[recipe_id]['vege_id'] = row[2]
            recipes[recipe_id]['steps'].append({
                'step_no': row[3],
                'description': row[4]
            })

        return jsonify(list(recipes.values()))

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)