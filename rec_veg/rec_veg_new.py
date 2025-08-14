import base64
from io import BytesIO
import numpy as np
import csv
import os
import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.utils import load_img, img_to_array


from tensorflow.keras.applications import efficientnet, mobilenet_v3

# --- 步驟 1: 載入模型與設定 ---
MODEL_PATH = os.path.join(os.path.dirname(__file__), '1best_tuned_model.keras')
CLASSES_CSV_PATH = os.path.join(os.path.dirname(__file__), 'classes_new.csv')

try:
    model = load_model(MODEL_PATH)
    print(f"✅ 模型 '{MODEL_PATH}' 載入成功。")
except Exception as e:
    print(f"❌ 模型載入失敗: {e}")
    model = None

model_architecture = 'MobileNetV3-Large'

if model_architecture == 'MobileNetV3-Large':
    preprocessing_function = mobilenet_v3.preprocess_input
    target_image_size = (224, 224)
    print("🚀 使用 MobileNetV3-Large 的預處理函式。")
else:
    raise ValueError("不支援的模型架構! 請選擇 'EfficientNet-B0' 或 'MobileNetV3-Large'")

# --- 步驟 2: 載入類別名稱 ---

def load_classes(csv_path=CLASSES_CSV_PATH):
    """
    從 CSV 檔案載入類別名稱。
    """
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            classes = [row[1] for row in reader]
        print(f"✅ 成功從 '{csv_path}' 載入 {len(classes)} 個類別。")
        return classes
    except FileNotFoundError:
        print(f"❌ 錯誤: 找不到類別檔案 '{csv_path}'。")
        return []
    except IndexError:
        print(f"❌ 錯誤: CSV 檔案 '{csv_path}' 格式不正確，請確保每行至少有一欄。")
        return []

# 載入類別名稱
class_names = load_classes(CLASSES_CSV_PATH)

# --- 步驟 3: 定義辨識函式 ---

def rec_veg(base64_string: str):
    """
    接收 Base64 編碼的圖片字串，進行解碼、預處理、預測，並回傳結果。

    Args:
        base64_string (str): Base64 編碼的圖片字串。

    Returns:
        dict: 例如 {"prediction": "高麗菜", "confidence": "97.12%"}；若發生錯誤則回傳 None。
    """
    if model is None or not class_names:
        print("❌ 模型或類別名稱未載入，無法進行預測。")
        return None

    try:
        # 處理 base64 字串，移除 data URI scheme (如果有的話)
        if isinstance(base64_string, str) and base64_string.startswith("data:image"):
            base64_string = base64_string.split(",")[1]

        image_bytes = base64.b64decode(base64_string)
        image_file = BytesIO(image_bytes)

        # 載入圖片並調整為模型需要的尺寸
        img = load_img(image_file, target_size=target_image_size)

        # 轉為 numpy 陣列並預處理
        img_array = img_to_array(img)
        img_array_expanded = np.expand_dims(img_array, axis=0)
        img_preprocessed = preprocessing_function(img_array_expanded)

        # 進行預測
        predictions = model.predict(img_preprocessed)
        scores = predictions[0]
        predicted_index = np.argmax(scores)
        predicted_class = class_names[predicted_index]
        confidence = float(np.max(scores) * 100.0)

        return {
            "prediction": predicted_class,
            "confidence": f"{confidence:.2f}%"
        }

    except Exception as e:
        print(f"❌ 預測過程中發生錯誤: {e}")
        return None


# --- 步驟 4: 執行辨識測試 ---
if __name__ == '__main__':
    try:
        image_path = "白苦瓜.jpg"
        with open(image_path, "rb") as img_file:
            b64_string = base64.b64encode(img_file.read()).decode('utf-8')

        print(f"\n🔍 正在辨識圖片: '{image_path}'...")
        prediction_result = rec_veg(b64_string)

        if prediction_result:
            print("\n--- 辨識結果 ---")
            print(f"🥒 預測類別: {prediction_result['prediction']}")
            print(f"📈 信心度: {prediction_result['confidence']}")
            print("------------------")

    except FileNotFoundError:
        print(f"❌ 測試錯誤: 找不到圖片檔案 '{image_path}'。請將圖片放在正確的路徑。")
    except Exception as e:
        print(f"❌ 執行時發生未知錯誤: {e}")