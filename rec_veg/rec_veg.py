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





class VegetablePredictor:
    """
    一個封裝了蔬菜辨識模型的類別。
    - 初始化時載入模型和類別。
    - 提供一個 predict 方法來進行預測。
    """

    def __init__(self, model_path, classes_path):
        """
        類別的建構函式，在物件被建立時執行。
        :param model_path: Keras 模型的檔案路徑。
        :param classes_path: classes.csv 的檔案路徑。
        """
        try:
            self.model = load_model(model_path)
            self.classes = self._load_classes(classes_path)
            print("模型和類別已成功載入到 VegetablePredictor 中。")
        except Exception as e:
            print(f"錯誤：初始化 VegetablePredictor 失敗。請檢查檔案路徑。")
            raise e

    def _load_classes(self, csv_path):
        """
        私有方法，從 CSV 檔案載入類別名稱。
        """
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            # 假設 CSV 第一行是標頭 (id, name)，所以從第二行開始讀取
            # 如果您的 CSV 沒有標頭，請將 [1:] 移除
            return [row[1] for row in list(reader)]

    def predict(self, base64_string):
        """
        對 Base64 編碼的圖片字串進行預測。
        :param base64_string: 圖片的 Base64 字串。
        :return: 一個包含預測結果的字典。
        """
        # 處理 base64 字串
        if base64_string.startswith("data:image"):
            base64_string = base64_string.split(",")[1]

        image_bytes = base64.b64decode(base64_string)
        image_file = BytesIO(image_bytes)

        # 載入圖片並前處理
        img = load_img(image_file, target_size=(128, 128))
        img_array = img_to_array(img) / 255.0
        img_array = tf.expand_dims(img_array, axis=0)

        # 預測
        preds = self.model.predict(img_array)
        pred_idx = tf.argmax(preds, axis=1).numpy()[0]
        confidence = tf.reduce_max(preds).numpy() * 100

        # 準備回傳的資料
        result = {
            "vegetable": self.classes[pred_idx],
            "confidence": f"{confidence:.2f}",
        }

        print(f"預測結果: {result}")
        return result