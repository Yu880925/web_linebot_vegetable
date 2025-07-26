import base64
from io import BytesIO
from tensorflow.keras.models import load_model
from tensorflow.keras.utils import load_img, img_to_array
import tensorflow as tf
import numpy as np
import csv
import os # 新增 os 模組

# 載入模型
current_dir = os.path.dirname(__file__)
model_path = os.path.join(current_dir, 'model_mnV2(best).keras')
model = load_model(model_path)

def load_classes(csv_path='classes.csv'):
    # 使用絕對路徑載入 classes.csv
    full_csv_path = os.path.join(os.path.dirname(__file__), csv_path)
    with open(full_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        return [row[1] for row in reader]

# 載入類別名稱
classes = load_classes('classes.csv')

def rec_veg(base64_string):
    try:
        # 處理 base64 字串
        if base64_string.startswith("data:image"):
            base64_string = base64_string.split(",")[1]
        image_bytes = base64.b64decode(base64_string)
        image_file = BytesIO(image_bytes)
        print(image_file)

        # 載入圖片並前處理
        img = load_img(image_file, target_size=(128, 128))
        img_array = img_to_array(img) / 255.0
        img_array = tf.expand_dims(img_array, axis=0)

        # 預測
        preds = model.predict(img_array)
        pred_idx = tf.argmax(preds, axis=1).numpy()[0]
        confidence = tf.reduce_max(preds).numpy() * 100

        print(f"預測類別：{classes[pred_idx]}")
        print(f"信心度：{confidence:.2f}%")

        # 修改回傳值為元組 (蔬菜名稱, 信心度)
        return f"預測類別：{classes[pred_idx]}\n信心度：{confidence:.2f}%"

    except Exception as e:
        print(f"rec_veg 函數中發生錯誤: {e}")
        return f"rec_veg 函數中發生錯誤: {e}"
