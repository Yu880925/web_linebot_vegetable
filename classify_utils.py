import tensorflow as tf
from tensorflow.keras.models import load_model
import numpy as np
from PIL import Image

# 模型初始化
model = load_model("my_veg_model_e8.h5")

# 假設你的類別順序（請根據實際訓練時的 class index 替換）
class_names = ["九層塔", "大白菜", "大陸妹", "娃娃菜", "小白菜", "山藥", "山蘇", "油菜", "空心菜", "筊白筍", "紅鳳菜", "絲瓜", "美生菜", "芋頭", "芥藍", "芹菜", "苦瓜", "茼蒿", "莧菜", "蒜頭", "蓮藕", "蘿蔓", "青江菜", "青花菜", "龍鬚菜"]

def predict_image(image_path):
    try:
        img = Image.open(image_path).convert('RGB')
        img = img.resize((224, 224))  # 根據你訓練時的大小調整
        img_array = np.array(img) / 255.0
        img_array = np.expand_dims(img_array, axis=0)

        predictions = model.predict(img_array)
        pred_class = class_names[np.argmax(predictions)]
        confidence = np.max(predictions)

        return f"辨識結果：{pred_class}\n信心度：{confidence:.2%}"
    except Exception as e:
        return f"圖片處理錯誤：{e}"
