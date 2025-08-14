import pandas as pd
import os
import re
import psycopg2
from dotenv import load_dotenv
import difflib # 引入 difflib 函式庫
from pypinyin import pinyin, Style

load_dotenv()


def get_db_connection():
    """建立並回傳 PostgreSQL 資料庫連線"""
    try:
        DATABASE_URL = os.getenv("DATABASE_URL")
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

def get_nutrient_columns_from_db(nutrient_name: str):
    """
    從資料庫的 nutrition_info 表格中，根據中文、拼音或別名進行模糊搜尋，
    回傳所有符合條件的英文欄位名稱和中文名稱。
    """
    conn = get_db_connection()
    if conn is None:
        return [], "錯誤：無法連接資料庫。"

    try:
        cursor = conn.cursor()
        search_term_lower = nutrient_name.strip().lower()
        
        query = """
            SELECT DISTINCT nutrition_en, nutrition_zh
            FROM nutrition_info
            WHERE 
                LOWER(nutrition_zh) LIKE %s OR 
                LOWER(pypinyin) LIKE %s OR 
                LOWER(alias) LIKE %s;
        """
        
        # 嘗試將使用者輸入的中文轉換成拼音，以增加搜尋成功率
        pinyin_search_term = "".join(
            [item[0] for item in pinyin(search_term_lower, style=Style.NORMAL)]
        )
        pinyin_search_term_with_wildcard = f"%{pinyin_search_term}%"

        cursor.execute(query, (f"%{search_term_lower}%", pinyin_search_term_with_wildcard, f"%{search_term_lower}%"))
        results = cursor.fetchall()

        if results:
            return results, None
        else:
            return [], f"找不到與 '{nutrient_name}' 相關的營養成分數據。"

    except Exception as e:
        print(f"Database query failed: {e}")
        return [], f"資料庫查詢失敗: {e}"
    finally:
        if conn:
            conn.close()


def get_top_vegetables_by_nutrient(nutrient_name: str, **kwargs):
    """
    根據指定的營養成分名稱，從資料庫中找出含量最高的三項蔬菜。
    此函式現可處理多個匹配的營養成分。
    """
    # 使用正規表達式拆分輸入字串，分隔符為逗號、空格或頓號
    nutrient_queries = re.split(r'[,，\s]', nutrient_name)
    nutrient_queries = [q.strip() for q in nutrient_queries if q.strip()]

    if not nutrient_queries:
        return "錯誤：無效的營養成分輸入。"

    conn = get_db_connection()
    if conn is None:
        return "錯誤：無法連接資料庫。"

    try:
        cursor = conn.cursor()
        final_results_list = []

        # 針對每一個拆分後的查詢詞進行處理
        for query_term in nutrient_queries:
            # 呼叫函式，獲取所有匹配的營養成分
            nutrient_matches, error_message = get_nutrient_columns_from_db(query_term)
            
            if error_message:
                print(f"DEBUG: {error_message}")
                continue
            
            # 針對每一個匹配的營養成分，都進行一次查詢
            for actual_nutrient_column, found_nutrient_name in nutrient_matches:
                print(f"DEBUG: 正在查詢營養成分: {found_nutrient_name}")
                # 1. 查詢 vege_nutrition，找出該營養成分含量最高的三項
                query_nutrition = f"""
                    SELECT vege_id, {actual_nutrient_column}, *
                    FROM vege_nutrition
                    ORDER BY {actual_nutrient_column} DESC
                    LIMIT 3;
                """
                cursor.execute(query_nutrition)
                nutrition_rows = cursor.fetchall()
                
                if not nutrition_rows:
                    continue

                col_names = [desc[0] for desc in cursor.description]

                vege_ids = [row[col_names.index('vege_id')] for row in nutrition_rows]
                
                # 2. 獲取所有相關 vege_id 的中文名稱和別名
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

                # 3. 格式化結果並添加到最終列表
                for row in nutrition_rows:
                    row_dict = dict(zip(col_names, row))
                    veg_id = row_dict['vege_id']
                    chinese_name = vege_id_to_name.get(veg_id, f"未知蔬菜 (ID: {veg_id})")
                    aliases = vege_id_to_aliases.get(veg_id, [])
                    nutrient_value = row_dict.get(actual_nutrient_column)
                    unit = actual_nutrient_column.split('_')[-1] if '_' in actual_nutrient_column else ''

                    all_nutrients_data = {k: v for k, v in row_dict.items() if k != 'vege_id'}

                    final_results_list.append({
                        "id": veg_id,
                        "chinese_name": chinese_name,
                        "nutrient_name": found_nutrient_name,
                        "nutrient_value": nutrient_value,
                        "unit": unit,
                        "aliases": aliases,
                        "all_nutrients": all_nutrients_data
                    })

        if not final_results_list:
            return f"找不到與 '{nutrient_name}' 相關的有效數據。"
        
        return final_results_list
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