import os
from flask import Flask, request, abort
from linebot.exceptions import InvalidSignatureError
from dotenv import load_dotenv

from linebot.v3.webhook import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi
from linebot.v3.webhooks.models import MessageEvent # 確保 MessageEvent 來自 webhooks.models
from linebot.v3.webhooks.models import TextMessageContent
from linebot.v3.webhooks.models import ImageMessageContent
import requests
import base64 # 新增 base64 模組

# 新增 logging 模組
import logging
from logging.handlers import RotatingFileHandler
import sys # 為了配置 StreamHandler 再次導入

# 確保 TextMessageContent 來自 webhooks.models
from linebot.v3.messaging.models import (
    ImageMessage, TextMessage, ReplyMessageRequest, QuickReply, QuickReplyItem,
    CameraAction, CameraRollAction, MessageAction,
    FlexMessage, FlexBubble, FlexCarousel, FlexImage, FlexBox,
    FlexText, FlexButton, URIAction
)
import uuid  # 新增 uuid 模組

# 新增日誌以確認 rec_veg 模組載入
app = Flask(__name__)

# 配置 Flask 應用程式的日誌
app.logger.setLevel(logging.INFO) # 設定日誌級別為 INFO
# 移除所有現有的處理器，避免重複日誌
for handler in app.logger.handlers:
    app.logger.removeHandler(handler)
# 添加一個 StreamHandler，將日誌輸出到標準輸出 (stdout)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
app.logger.addHandler(handler)


app.logger.info("Attempting to import rec_veg...")
from rec_veg.rec_veg import rec_veg # 匯入辨識函數
app.logger.info("rec_veg imported successfully.")

from nutri_rec.nutri_rec import get_top_vegetables_by_nutrient, get_vegetables_by_name_or_alias
import pandas as pd # 新增 pandas 模組

load_dotenv()

# 定義營養成分的中英文對應，用於格式化輸出
NUTRIENT_DISPLAY_MAPPING = {
    "熱量": "calories_kcal",
    "水": "water_g",
    "蛋白質": "protein_g",
    "脂肪": "fat_g",
    "碳水化合物": "carb_g",
    "膳食纖維": "fiber_g",
    "糖": "sugar_g",
    "鈉": "sodium_mg",
    "鉀": "potassium_mg",
    "鈣": "calcium_mg",
    "鎂": "magnesium_mg",
    "鐵": "iron_mg",
    "鋅": "zinc_mg",
    "磷": "phosphorus_mg",
    "維生素A": "vitamin_a_iu",
    "維生素C": "vitamin_c_mg",
    "維生素E": "vitamin_e_mg",
    "維生素B1": "vitamin_b1_mg",
    "葉酸": "folic_acid_ug",
}

UNIT_ABBREVIATION_TO_CHINESE = {
    'kcal': '大卡',
    'g': '克',
    'mg': '毫克',
    'iu': 'IU',
    'ug': '微克',
}

# Helper function for creating Flex Message
def _create_vegetable_flex_message(veg_data_list, alt_text_prefix, is_nutrient_search=False):
    bubbles = []
    for veg_data in veg_data_list:
        aliases_text = "別名：" + ", ".join(veg_data['aliases']) if veg_data['aliases'] else "無別名"
        all_nutrients_detail = []
        # Assuming veg_data['all_nutrients'] is a dictionary
        for i, (nutrient_key, nutrient_value) in enumerate(veg_data['all_nutrients'].items()):
            if i < 2:  # Skip first two
                continue
            if i >= 7:  # Limit to 5 nutrients (2 to 6)
                break
            display_name = NUTRIENT_DISPLAY_MAPPING.get(nutrient_key, "")
            if not display_name:
                display_name = nutrient_key.split('_')[0].capitalize()

            current_unit_abbreviation = nutrient_key.split('_')[-1] if '_' in nutrient_key else ''
            current_unit = UNIT_ABBREVIATION_TO_CHINESE.get(current_unit_abbreviation, '')

            if pd.isna(nutrient_value):
                nutrient_value_display = "N/A"
            else:
                nutrient_value_display = f"{nutrient_value:.1f}" if isinstance(nutrient_value, (int, float)) else str(nutrient_value)
            all_nutrients_detail.append(f"{display_name}：{nutrient_value_display}{current_unit}")

        all_nutrients_text = "營養資訊(每100 克可食部分)：\n" + "\n".join(all_nutrients_detail)

        bubble_body_contents = [
            FlexText(text=veg_data['chinese_name'], weight='bold', size='xl'),
            FlexText(text=aliases_text, size='sm', color='#aaaaaa', wrap=True, margin='sm'),
            FlexText(text=all_nutrients_text, size='sm', color='#555555', wrap=True, margin='md')
        ]

        # Conditionally add nutrient search specific text
        if is_nutrient_search and 'nutrient_name' in veg_data and 'nutrient_value' in veg_data and 'unit' in veg_data:
            bubble_body_contents.insert(1, FlexText(text=f"查詢成分：{veg_data['nutrient_name']} {veg_data['nutrient_value']}{veg_data['unit']}", size='md', margin='md'))

        bubble = FlexBubble(
            direction='ltr',
            hero=FlexImage(
                url=f"https://via.placeholder.com/450x300?text={veg_data['chinese_name']}",
                size='full',
                aspect_ratio='1.5:1',
                aspect_mode='cover',
                action=URIAction(uri="https://example.com", label="圖片連結")
            ),
            body=FlexBox(
                layout='vertical',
                contents=bubble_body_contents
            ),
            footer=FlexBox(
                layout='vertical',
                spacing='sm',
                contents=[
                    FlexButton(
                        style='link',
                        height='sm',
                        action=MessageAction(label='查看相關食譜', text='查看相關食譜')
                    ),
                    FlexButton(
                        style='link',
                        height='sm',
                        action=URIAction(label='前往網站看得更詳細', uri='https://example.com')
                    )
                ]
            )
        )
        bubbles.append(bubble)

    if not bubbles:
        return TextMessage(text="沒有找到符合條件的蔬菜。")  # Fallback to text message if no bubbles
    else:
        return FlexMessage(
            alt_text=f"{alt_text_prefix}相關蔬菜",
            contents=FlexCarousel(contents=bubbles)
        )



LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN') # 移除預設值
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET') # 移除預設值

# 確保環境變數已載入，否則應用程式無法啟動
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not set in environment variables.")

app.logger.info(f"LINE_CHANNEL_ACCESS_TOKEN loaded (length: {len(LINE_CHANNEL_ACCESS_TOKEN)})")
app.logger.info(f"LINE_CHANNEL_SECRET loaded (length: {len(LINE_CHANNEL_SECRET)})")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    app.logger.info("Request signature: " + signature)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Request body: " + body)
        # 如果是簽名錯誤，直接返回 400，並停止進一步處理
        abort(400)
    except Exception as e:
        import traceback
        app.logger.error(f"Unhandled exception in callback: {e}") # 更新錯誤訊息
        app.logger.error(traceback.format_exc())
        abort(500)
    return 'OK'

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    app.logger.info("進入 handle_image_message 函數 - 步驟 1") # 改回 app.logger.info

    image_filename = f'temp_image_{uuid.uuid4()}.jpg'
    try:
        app.logger.info("嘗試從 LINE API 下載圖片 - 步驟 2") # 改回 app.logger.info
        # 手動發 request 去 LINE 拿圖片內容
        headers = {
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
        }
        url = f"https://api-data.line.me/v2/bot/message/{event.message.id}/content"
        response = requests.get(url, headers=headers, stream=True)

        if response.status_code != 200:
            app.logger.info(f"圖片下載失敗，狀態碼：{response.status_code} - 步驟 3") # 改回 app.logger.info
            raise Exception(f"圖片下載失敗，狀態碼：{response.status_code}")

        app.logger.info(f"圖片下載成功，正在寫入臨時檔案: {image_filename} - 步驟 4") # 改回 app.logger.info
        with open(image_filename, 'wb') as f:
            for chunk in response.iter_content():
                f.write(chunk)

        app.logger.info(f"臨時檔案寫入完成，正在轉換為 Base64 字串. File size: {os.path.getsize(image_filename)} bytes - 步驟 5") # 改回 app.logger.info
        # 將圖片轉換為 Base64 字串
        with open(image_filename, 'rb') as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        app.logger.info("Base64 字串轉換完成，準備呼叫 rec_veg。 - 步驟 6") # 改回 app.logger.info

        # 呼叫模型進行預測
        recognition_result = rec_veg(encoded_string)
        app.logger.info(f"rec_veg recognition_result: {recognition_result} - 步驟 7") # 改回 app.logger.info

        # 解析 rec_veg 函式回傳的字串格式 "預測類別：[蔬菜名稱]\n信心度：[信心度]%"
        veg_name = "未知蔬菜"
        confidence = 0.0

        try:
            lines = recognition_result.split('\n')
            if len(lines) >= 2:
                # 解析蔬菜名稱
                if "預測類別：" in lines[0]:
                    veg_name = lines[0].replace("預測類別：", "").strip()

                # 解析信心度
                if "信心度：" in lines[1]:
                    confidence_str = lines[1].replace("信心度：", "").replace("%", "").strip()
                    confidence = float(confidence_str) / 100.0 # 轉換為0-1之間的小數

        except Exception as e:
            app.logger.error(f"解析 recognition_result 失敗: {e}") # 修改 print
            import traceback # 確保導入
            app.logger.error(traceback.format_exc()) # 打印追溯
            # 如果解析失敗，使用預設值
            veg_name = "未知蔬菜"
            confidence = 0.0

        prefix_message_text = ""
        if confidence >= 0.8:
            prefix_message_text = f"哼哼 根據我的判斷 它就是\"{veg_name}\"!!"
            if confidence == 1.0:
                prefix_message_text = f"真相只有一個 就是\"{veg_name}\"!!"
        elif confidence >= 0.5:
            prefix_message_text = f"可能是\"{veg_name}\"   也許讓我再看更清楚的一張"
        else:
            prefix_message_text = "歐內該  請提供更清晰的"
            

        # 在訊息最後加上信心度 (如果信心度大於等於50%)
        if confidence >= 0.5:
            prefix_message_text += f"\n我有{confidence*100:.0f}%的信心"

        # 根據辨識結果獲取蔬菜詳細資訊
        vegetable_details = get_vegetables_by_name_or_alias(
            veg_name, # 將辨識到的蔬菜名稱作為搜尋詞
            nutrition_obj_name='vege_nutrition_202507211504.xlsx',
            basic_vege_obj_name='basic_vege_202507211504_good.xlsx',
            alias_obj_name='vege_alias_202507211504.xlsx'
        )

        messages_to_reply = [TextMessage(text=prefix_message_text)]

        # 如果信心度大於等於50%，才顯示字卡
        if confidence >= 0.5 and vegetable_details and not isinstance(vegetable_details, str): # 如果有找到蔬菜資料
            flex_message = _create_vegetable_flex_message(vegetable_details, f"辨識結果：{veg_name}")
            if flex_message: # 確保 flex_message 不是 None 或錯誤訊息
                messages_to_reply.append(flex_message)
        elif confidence < 0.5:
            # 如果信心度小於50%，則不顯示字卡，只顯示文字訊息
            pass # 這裡不需要做任何事，因為上面已經設定了文字訊息
        else:
            messages_to_reply.append(TextMessage(text="未能找到該蔬菜的詳細資訊。"))

        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=messages_to_reply
            )
        )
        app.logger.info("Image recognition reply sent successfully.") # 修改 print
    except Exception as e:
        app.logger.info(f"Error processing image or sending reply: {e} - 步驟 8") # 改回 app.logger.info
        import traceback # 確保導入
        app.logger.info(traceback.format_exc()) # 改回 app.logger.info
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=f"圖片處理失敗：{e}")]  # 可以換成更可愛一點的錯誤訊息～？
            )
        )
    finally:
        if os.path.exists(image_filename):
            os.remove(image_filename)
            app.logger.info(f"Deleted temporary image file: {image_filename} - 步驟 9") # 改回 app.logger.info

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    print(f"Received text: {event.message.text}")
    try:
        if event.message.text == "上傳圖片":
            reply_message = TextMessage(
                text="請選擇拍照或從相簿選擇圖片(請盡量讓背景單純)：",
                quick_reply=QuickReply(
                    items=[
                        QuickReplyItem(action=CameraAction(label="開啟相機")),
                        QuickReplyItem(action=CameraRollAction(label="從相簿選擇"))
                    ]
                )
            )
        elif event.message.text == "輸入營養成分":
            reply_message = TextMessage(
                text="請輸入您想查詢的營養成分，例如：蛋白質、維生素C、鐵質\n您也可以輸入蔬菜名稱或別名，例如：高麗菜、大白菜"
            )
        else:
            nutrient_input = event.message.text.strip()
            recommendation_result = get_top_vegetables_by_nutrient(
                nutrient_input,
                nutrition_obj_name='vege_nutrition_202507211504.xlsx', # 修改為物件名稱
                basic_vege_obj_name='basic_vege_202507211504_good.xlsx', # 修改為物件名稱
                alias_obj_name='vege_alias_202507211504.xlsx' # 修改為物件名稱
            )

            if not recommendation_result or isinstance(recommendation_result, str): # 如果營養成分查詢無結果或有錯誤
                # 嘗試進行蔬菜名稱或別名查詢
                vegetable_search_result = get_vegetables_by_name_or_alias(
                    nutrient_input, # 將使用者輸入作為搜尋詞
                    nutrition_obj_name='vege_nutrition_202507211504.xlsx', # 修改為物件名稱
                    basic_vege_obj_name='basic_vege_202507211504_good.xlsx', # 修改為物件名稱
                    alias_obj_name='vege_alias_202507211504.xlsx' # 修改為物件名稱
                )
                if not vegetable_search_result or isinstance(vegetable_search_result, str): # 如果蔬菜名稱查詢也無結果或有錯誤
                    reply_message = TextMessage(text="沒有找到符合條件的營養成分或蔬菜。請檢查您的輸入。")
                else:
                    # 限制蔬菜名稱查詢結果的數量，最多12個
                    limited_vegetable_search_result = vegetable_search_result[:12]
                    reply_message = _create_vegetable_flex_message(limited_vegetable_search_result, f"為您推薦 {nutrient_input} 相關蔬菜")

            else:
                # 使用營養成分查詢結果來構建 Flex Message
                reply_message = _create_vegetable_flex_message(recommendation_result, f"為您推薦 {nutrient_input} 含量最高的蔬菜", is_nutrient_search=True)

        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[reply_message]
            )
        )
        print("Reply sent successfully.")
    except Exception as e:
        print(f"Failed to reply: {e}")





if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 




