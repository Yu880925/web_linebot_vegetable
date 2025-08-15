import base64
from io import BytesIO
from tensorflow.keras.models import load_model
from tensorflow.keras.utils import load_img, img_to_array
import tensorflow as tf
import numpy as np
import csv
import os 
from tensorflow.keras.applications import efficientnet, mobilenet_v3

# 載入模型
current_dir = os.path.dirname(__file__)
model_path = os.path.join(current_dir, '1best_tuned_model.keras')
model = load_model(model_path)

def load_classes(csv_path='classes.csv'):
    # 使用絕對路徑載入 classes.csv
    full_csv_path = os.path.join(os.path.dirname(__file__), csv_path)
    with open(full_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        return [row[1] for row in reader]

# 載入類別名稱
classes = load_classes('classes.csv')

def rec_veg(base64_string: str):
    """
    接收 Base64 編碼的圖片字串，進行解碼、預處理、預測，並回傳結果。
    
    Args:
        base64_string (str): Base64 編碼的圖片字串。

    Returns:
        dict: 一個包含 'prediction' 和 'confidence' 的字典，如果出錯則回傳 None。
    """
    if not class_names:
        print("❌ 類別名稱未載入，無法進行預測。")
        return None

    try:
        # 處理 base64 字串，移除 data URI scheme (如果有的話)
        if base64_string.startswith("data:image"):
            base64_string = base64_string.split(",")[1]
        
        image_bytes = base64.b64decode(base64_string)
        image_file = BytesIO(image_bytes)

        # 載入圖片並調整為模型需要的尺寸
        # 修正: 從 (128, 128) 改為訓練時使用的 target_image_size
        img = load_img(image_file, target_size=target_image_size)
        
        # 將圖片轉換為 numpy 陣列
        img_array = img_to_array(img)
        
        # 擴展維度以符合模型輸入格式 (batch_size, height, width, channels)
        img_array_expanded = np.expand_dims(img_array, axis=0)
        
        # *** 關鍵修正 ***
        # 使用與訓練時完全相同的預處理函式
        img_preprocessed = preprocessing_function(img_array_expanded)

        # 進行預測
        predictions = model.predict(img_preprocessed)
        
        # 解析預測結果
        scores = predictions[0]
        predicted_index = np.argmax(scores)
        predicted_class = class_names[predicted_index]
        confidence = np.max(scores) * 100
        
        result = {
            "prediction": predicted_class,
            "confidence": f"{confidence:.2f}%"
        }
        return result

    except Exception as e:
        print(f"❌ 預測過程中發生錯誤: {e}")
        return None






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

    def load_classes(csv_path='classes_new.csv'):
        """
        從 CSV 檔案載入類別名稱。
        修正: 從 row[1] 改為 row[0] 來讀取正確的欄位。
        """
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                # 假設每個類別名稱佔據一行中的第一欄
                classes = [row[1] for row in reader]
            print(f"✅ 成功從 '{csv_path}' 載入 {len(classes)} 個類別。")
            return classes
        except FileNotFoundError:
            print(f"❌ 錯誤: 找不到類別檔案 '{csv_path}'。")
            return []
        except IndexError:
            print(f"❌ 錯誤: CSV 檔案 '{csv_path}' 格式不正確，請確保每行至少有一欄。")
            return []

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