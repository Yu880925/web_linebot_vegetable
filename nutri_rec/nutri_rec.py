import pandas as pd
import os
import re
import psycopg2 # 新增
from dotenv import load_dotenv

load_dotenv()

# 新增營養成分名稱的中文到英文映射
NUTRIENT_MAPPING = {
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


def get_db_connection():
    """建立並回傳 PostgreSQL 資料庫連線"""
    try:
        DATABASE_URL = os.getenv("DATABASE_URL")
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

def get_top_vegetables_by_nutrient(nutrient_name: str, **kwargs):
    """
    根據指定的營養成分名稱，從資料庫中找出含量最高的五項蔬菜。
    """
    conn = get_db_connection()
    if conn is None:
        return "錯誤：無法連接資料庫。"

    try:
        cursor = conn.cursor()

        # 嘗試透過映射字典獲取對應的英文欄位名稱
        actual_nutrient_column = NUTRIENT_MAPPING.get(nutrient_name)
        input_nutrient_lower = nutrient_name.lower().strip()

        # 確定實際使用的營養成分欄位名稱
        if actual_nutrient_column:
            pass
        elif input_nutrient_lower in NUTRIENT_MAPPING.values():
            actual_nutrient_column = input_nutrient_lower
        else:
            return f"錯誤：找不到營養成分 '{nutrient_name}' 的數據。請檢查輸入是否正確或檔案中是否存在該營養成分。"

        # 1. 查詢 vege_nutrition，找出該營養成分含量最高的五項
        query_nutrition = f"""
            SELECT vege_id, {actual_nutrient_column}, *
            FROM vege_nutrition
            ORDER BY {actual_nutrient_column} DESC
            LIMIT 5;
        """
        cursor.execute(query_nutrition)
        nutrition_rows = cursor.fetchall()

        if not nutrition_rows:
            return f"找不到 '{nutrient_name}' 的有效數值數據。"

        # 取得所有欄位名稱
        col_names = [desc[0] for desc in cursor.description]

        # 2. 獲取所有相關 vege_id 的中文名稱和別名
        vege_ids = [row[col_names.index('vege_id')] for row in nutrition_rows]
        
        query_basic = "SELECT id, vege_name FROM basic_vege WHERE id = ANY(%s);"
        cursor.execute(query_basic, (vege_ids,))
        basic_vege_rows = cursor.fetchall()
        vege_id_to_name = {row[0]: row[1] for row in basic_vege_rows}

        query_alias = "SELECT vege_id, alias FROM vege_alias WHERE vege_id = ANY(%s) AND type NOT IN ('羅馬拼音', '錯字');"
        cursor.execute(query_alias, (vege_ids,))
        alias_rows = cursor.fetchall()
        vege_id_to_aliases = {}
        for row in alias_rows:
            vege_id, alias = row
            if vege_id not in vege_id_to_aliases:
                vege_id_to_aliases[vege_id] = []
            vege_id_to_aliases[vege_id].append(alias)

        # 3. 格式化結果
        results_list = []
        for row in nutrition_rows:
            row_dict = dict(zip(col_names, row))
            veg_id = row_dict['vege_id']
            chinese_name = vege_id_to_name.get(veg_id, f"未知蔬菜 (ID: {veg_id})")
            aliases = vege_id_to_aliases.get(veg_id, [])
            nutrient_value = row_dict.get(actual_nutrient_column)
            unit = actual_nutrient_column.split('_')[-1] if '_' in actual_nutrient_column else ''

            all_nutrients_data = {k: v for k, v in row_dict.items() if k != 'vege_id'}

            results_list.append({
                "id": veg_id,
                "chinese_name": chinese_name,
                "nutrient_name": nutrient_name,
                "nutrient_value": nutrient_value,
                "unit": unit,
                "aliases": aliases,
                "all_nutrients": all_nutrients_data
            })

        return results_list
    except Exception as e:
        print(f"Database query failed: {e}")
        return f"資料庫查詢失敗: {e}"
    finally:
        if conn:
            conn.close()

def get_vegetables_by_name_or_alias(search_term: str, **kwargs):
    conn = get_db_connection()
    if conn is None:
        return "錯誤：無法連接資料庫。"

    try:
        cursor = conn.cursor()
        search_term_lower = f"%{search_term.strip()}%"
        
        # 1. 聯合查詢 basic_vege 和 vege_alias，找出匹配的 vege_id
        query_vege_ids = """
            SELECT DISTINCT id FROM basic_vege WHERE vege_name ILIKE %s
            UNION
            SELECT DISTINCT vege_id FROM vege_alias WHERE alias ILIKE %s;
        """
        cursor.execute(query_vege_ids, (search_term_lower, search_term_lower))
        matched_vege_ids = [row[0] for row in cursor.fetchall()]

        if not matched_vege_ids:
            return []

        results_list = []
        for vege_id in matched_vege_ids:
            # 2. 針對每個 vege_id 獲取詳細資訊
            query_detail = """
                SELECT * FROM basic_vege WHERE id = %s;
            """
            cursor.execute(query_detail, (vege_id,))
            basic_vege_row = cursor.fetchone()
            if not basic_vege_row:
                continue
            
            basic_vege_cols = [desc[0] for desc in cursor.description]
            basic_vege_dict = dict(zip(basic_vege_cols, basic_vege_row))
            chinese_name = basic_vege_dict.get('vege_name')

            query_nutrition = """
                SELECT * FROM vege_nutrition WHERE vege_id = %s;
            """
            cursor.execute(query_nutrition, (vege_id,))
            nutrition_row = cursor.fetchone()
            nutrition_cols = [desc[0] for desc in cursor.description]
            nutrition_dict = dict(zip(nutrition_cols, nutrition_row)) if nutrition_row else {}

            query_aliases = """
                SELECT alias FROM vege_alias WHERE vege_id = %s AND type NOT IN ('羅馬拼音', '錯字');
            """
            cursor.execute(query_aliases, (vege_id,))
            aliases = [row[0] for row in cursor.fetchall()]
            
            # 合併營養數據，並去除重複的 vege_id 欄位
            all_nutrients = {k: v for k, v in nutrition_dict.items() if k != 'vege_id'}
            
            results_list.append({
                'id': vege_id,
                'chinese_name': chinese_name,
                'aliases': aliases,
                'all_nutrients': all_nutrients,
                'nutrient_name': "總覽",
                'nutrient_value': None,
                'unit': ""
            })
        
        return results_list
    except Exception as e:
        print(f"Database query failed: {e}")
        return f"資料庫查詢失敗: {e}"
    finally:
        if conn:
            conn.close()

# 為了在 `app.py` 中調用時保持一致，這裡保留了原本的函數名稱。
# 函式簽名也進行了調整，不再需要 `nutrition_obj_name` 等參數。
# 這邊的 **kwargs 是為了相容於 app.py 裡的呼叫方式，實質上沒有使用
# 在 app.py 裡，這些參數會被忽略。