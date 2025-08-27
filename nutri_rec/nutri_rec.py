import pandas as pd
import os
import re
import psycopg2
from dotenv import load_dotenv
import difflib # 引入 difflib 函式庫
from pypinyin import pinyin, Style
from thefuzz import fuzz, process
import json
import redis.exceptions

# 根據你的專案結構，從父層資料夾引入 redis_client 模組
from redis_client import get_redis_connection

# 取得 Redis 連線實例
r = get_redis_connection()

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
    使用 thefuzz 實現更精確的模糊匹配。
    搜尋邏輯：
    1. 先中文比對 nutrition_zh
    2. 然後比對拼音 pypinyin  
    3. 最後再中文比對 alias
    回傳所有符合條件的英文欄位名稱和中文名稱。
    """
    conn = get_db_connection()
    if conn is None:
        return [], "錯誤：無法連接資料庫。"

    try:
        cursor = conn.cursor()
        search_term = nutrient_name.strip()
        search_term_lower = search_term.lower()
        
        # 將使用者輸入轉換成拼音
        pinyin_search_term = "".join(
            [item[0] for item in pinyin(search_term, style=Style.NORMAL)]
        )
        
        # 獲取所有營養成分資料
        query = """
            SELECT DISTINCT nutrition_en, nutrition_zh, pypinyin, alias
            FROM nutrition_info
            WHERE nutrition_zh IS NOT NULL OR pypinyin IS NOT NULL OR alias IS NOT NULL;
        """
        cursor.execute(query)
        all_nutrients = cursor.fetchall()
        
        print(f"DEBUG: 從資料庫獲取到 {len(all_nutrients)} 筆營養成分資料")
        
        if not all_nutrients:
            return [], f"找不到營養成分資料。"
        
        # 除錯：檢查是否有「蛋白質」相關的資料
        protein_related = [row for row in all_nutrients if '蛋白' in str(row)]
        print(f"DEBUG: 找到 {len(protein_related)} 筆包含「蛋白」的資料:")
        for row in protein_related[:5]:  # 只顯示前5筆
            print(f"  {row}")
        
        # 準備搜尋候選清單
        candidates = []
        for row in all_nutrients:
            nutrition_en, nutrition_zh, pypinyin_val, alias_val = row
            candidates.append({
                'nutrition_en': nutrition_en,
                'nutrition_zh': nutrition_zh,
                'pypinyin': pypinyin_val,
                'alias': alias_val
            })
        
        # 步驟1: 中文比對 nutrition_zh
        zh_candidates = [c for c in candidates if c['nutrition_zh']]
        zh_texts = [c['nutrition_zh'] for c in zh_candidates]
        
        # 除錯：檢查是否有完全匹配
        exact_match = None
        for candidate in zh_candidates:
            if candidate['nutrition_zh'] == search_term:
                exact_match = candidate
                break
        
        zh_matches = process.extract(
            search_term, 
            zh_texts, 
            scorer=fuzz.ratio, 
            limit=10
        )
        
        print(f"DEBUG: 搜尋詞 '{search_term}' 的中文匹配結果:")
        for text, score in zh_matches:
            print(f"  '{text}': {score}%")
        
        # 篩選高相似度的結果 
        good_zh_matches = []
        for text, score in zh_matches:
            if score >= 80:
                matching_candidate = next(c for c in zh_candidates if c['nutrition_zh'] == text)
                good_zh_matches.append((matching_candidate, score, 'zh'))
        
        # 如果有完全匹配，優先加入
        if exact_match:
            good_zh_matches.insert(0, (exact_match, 100, 'exact'))
        
        # 如果中文比對結果不夠好，進行步驟2: 拼音比對
        pinyin_matches = []
        if len(good_zh_matches) < 5:  # 如果中文匹配結果少於5個
            pinyin_candidates = [c for c in candidates if c['pypinyin']]
            pinyin_texts = [c['pypinyin'] for c in pinyin_candidates]
            pinyin_matches_raw = process.extract(
                pinyin_search_term, 
                pinyin_texts, 
                scorer=fuzz.ratio, 
                limit=10
            )
            
            # 篩選高相似度的拼音結果
            for text, score in pinyin_matches_raw:
                if score >= 80:
                    matching_candidate = next(c for c in pinyin_candidates if c['pypinyin'] == text)
                    pinyin_matches.append((matching_candidate, score, 'pinyin'))
        
        # 步驟3: 中文比對 alias
        alias_matches = []
        alias_candidates = [c for c in candidates if c['alias']]
        alias_texts = [c['alias'] for c in alias_candidates]
        alias_matches_raw = process.extract(
            search_term, 
            alias_texts, 
            scorer=fuzz.ratio, 
            limit=10
        )
        
        # 篩選高相似度的別名結果
        for text, score in alias_matches_raw:
            if score >= 80:
                matching_candidate = next(c for c in alias_candidates if c['alias'] == text)
                alias_matches.append((matching_candidate, score, 'alias'))
        
        # 合併所有結果，去重並按相似度排序
        all_matches = good_zh_matches + pinyin_matches + alias_matches
        
        # 去重：根據 nutrition_en 去重，保留最高分數的結果
        unique_matches = {}
        for candidate, score, match_type in all_matches:
            nutrition_en = candidate['nutrition_en']
            if nutrition_en not in unique_matches or score > unique_matches[nutrition_en][1]:
                unique_matches[nutrition_en] = (candidate, score, match_type)
        
        sorted_matches = sorted(unique_matches.values(), key=lambda x: x[1], reverse=True)[:1]
        
        print(f"DEBUG: 最終匹配結果:")
        for candidate, score, match_type in sorted_matches:
            print(f"  {candidate['nutrition_en']} ({candidate['nutrition_zh']}): {score}% [{match_type}]")
        
        # 格式化結果
        results = []
        for candidate, score, match_type in sorted_matches:
            results.append((candidate['nutrition_en'], candidate['nutrition_zh']))
        
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


# In nutri_rec.py

# In nutri_rec.py

def get_top_vegetables_by_nutrient(nutrient_name: str, **kwargs):
    """
    【修改後版本 v2】
    處理複合查詢、單一蔬菜查詢、以及營養素排行查詢。
    """
    redis_conn = get_redis_connection()
    query_string = nutrient_name.strip()
    cache_key = f"nutrient_search:{query_string}"

    if redis_conn:
        try:
            cached_result = redis_conn.get(cache_key)
            if cached_result:
                print(f"快取命中 (HIT) - Key: {cache_key}")
                return json.loads(cached_result)
        except Exception as e:
            print(f"從 Redis 讀取失敗: {e}")

    words = re.split(r'[,，\s]+', query_string)
    
    potential_veg_words = []
    potential_nutrient_words = []
    
    for word in words:
        veg_check = get_vegetables_by_name_or_alias(word)
        if veg_check and isinstance(veg_check, list) and len(veg_check) > 0:
            potential_veg_words.append({'word': word, 'data': veg_check[0]})
        
        nutrient_check, _ = get_nutrient_columns_from_db(word)
        if nutrient_check and len(nutrient_check) > 0:
            potential_nutrient_words.append({'word': word, 'data': nutrient_check})

    # === 路徑 A: 精準查詢 (找到一個蔬菜和至少一個營養素) ===
    if len(potential_veg_words) == 1 and len(potential_nutrient_words) > 0:
        veg_info = potential_veg_words[0]['data']
        nutrient_query_str = " ".join([n['word'] for n in potential_nutrient_words])
        nutrient_matches, _ = get_nutrient_columns_from_db(nutrient_query_str)
        
        if nutrient_matches:
            actual_nutrient_column, found_nutrient_name = nutrient_matches[0]
            all_nutrients = veg_info.get('all_nutrients', {})
            nutrient_value = all_nutrients.get(actual_nutrient_column)
            unit = actual_nutrient_column.split('_')[-1] if '_' in actual_nutrient_column else ''
            
            veg_info['nutrient_name'] = found_nutrient_name
            veg_info['nutrient_value'] = nutrient_value
            veg_info['unit'] = unit
            
            final_result = [veg_info]

            if redis_conn:
                try:
                    redis_conn.set(cache_key, json.dumps(final_result, default=str), ex=3600)
                    print(f"快取寫入 (SET) [精準查詢] - Key: {cache_key}")
                except Exception as e:
                    print(f"寫入 Redis 失敗: {e}")
            
            return final_result

    # === 【新增判斷路徑】路徑 B: 單一蔬菜通用資訊查詢 ===
    if len(potential_veg_words) == 1 and len(potential_nutrient_words) == 0:
        # 直接回傳 get_vegetables_by_name_or_alias 找到的蔬菜資訊
        final_result = [potential_veg_words[0]['data']]
        
        if redis_conn:
            try:
                redis_conn.set(cache_key, json.dumps(final_result, default=str), ex=3600)
                print(f"快取寫入 (SET) [單一蔬菜查詢] - Key: {cache_key}")
            except Exception as e:
                print(f"寫入 Redis 失敗: {e}")
        
        return final_result

    # === 路徑 C: 後備的排名查詢 ===
    conn = get_db_connection()
    if conn is None:
        return "錯誤：無法連接資料庫。"

    try:
        cursor = conn.cursor()
        grouped_results = {}
        
        nutrient_matches, error_message = get_nutrient_columns_from_db(query_string)
        
        if error_message and not nutrient_matches:
            return f"找不到與 '{query_string}' 相關的有效數據。"
            
        for actual_nutrient_column, found_nutrient_name in nutrient_matches:
            # (此處的排名查詢邏輯保持不變)
            if found_nutrient_name in grouped_results:
                continue
            
            query_nutrition = f"""
                SELECT vege_id, {actual_nutrient_column}, *
                FROM vege_nutrition
                WHERE {actual_nutrient_column} IS NOT NULL
                ORDER BY {actual_nutrient_column} DESC
                LIMIT 3;
            """
            cursor.execute(query_nutrition)
            nutrition_rows = cursor.fetchall()

            if not nutrition_rows: continue

            col_names = [desc[0] for desc in cursor.description]
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

            nutrient_results = []
            for row in nutrition_rows:
                row_dict = dict(zip(col_names, row))
                veg_id = row_dict['vege_id']
                nutrient_value = row_dict.get(actual_nutrient_column)
                unit = actual_nutrient_column.split('_')[-1] if '_' in actual_nutrient_column else ''

                nutrient_results.append({
                    "id": veg_id,
                    "chinese_name": vege_id_to_name.get(veg_id, f"未知蔬菜 (ID: {veg_id})"),
                    "nutrient_name": found_nutrient_name,
                    "nutrient_value": nutrient_value,
                    "unit": unit,
                    "aliases": vege_id_to_aliases.get(veg_id, []),
                    "all_nutrients": {k: v for k, v in row_dict.items() if k != 'vege_id'}
                })
            
            grouped_results[found_nutrient_name] = nutrient_results

        if not grouped_results:
            return f"找不到與 '{query_string}' 相關的有效數據。"
        
        final_results_list = []
        for results in grouped_results.values():
            final_results_list.extend(results)
        
        if redis_conn:
            try:
                redis_conn.set(cache_key, json.dumps(final_results_list, default=str), ex=3600)
                print(f"快取寫入 (SET) [排名查詢] - Key: {cache_key}")
            except Exception as e:
                print(f"寫入 Redis 失敗: {e}")
        
        return final_results_list
    except Exception as e:
        print(f"Database query failed: {e}")
        return f"資料庫查詢失敗: {e}"
    finally:
        if conn:
            conn.close()


def get_vegetables_by_name_or_alias(search_term: str, **kwargs):
    """
    根據蔬菜名稱或別名進行模糊搜尋，找出最相關的蔬菜。
    使用 thefuzz 實現模糊匹配。
    搜尋邏輯：
    1. 先比對中文名稱 (basic_vege.vege_name)、常見別名、其他學名 (vege_alias)
    2. 然後比對羅馬拼音 (vege_alias)
    3. 最後比對錯字 (vege_alias)
    回傳所有符合條件的蔬菜詳細資訊。
    """

    redis_conn = get_redis_connection()
    cache_key = f"veg_name:{search_term.strip()}"
    
    if redis_conn:
        try:
            cached_result = redis_conn.get(cache_key)
            if cached_result:
                print(f"快取命中 (HIT) - Key: {cache_key}")
                return json.loads(cached_result) # 從 JSON 字串還原成 Python 物件
        except Exception as e:
            print(f"從 Redis 讀取失敗: {e}")

    conn = get_db_connection()
    if conn is None:
        return "錯誤：無法連接資料庫。"

    try:
        cursor = conn.cursor()
        clean_search_term = search_term.strip()

        # --- 步驟 1: 獲取所有候選蔬菜資料 ---
        query_candidates = """
            SELECT id AS vege_id, vege_name AS alias, '中文名稱' AS type FROM basic_vege
            UNION ALL
            SELECT vege_id, alias, type FROM vege_alias;
        """
        cursor.execute(query_candidates)
        all_aliases = cursor.fetchall()

        if not all_aliases:
            return [] # 資料庫為空

        candidates = []
        for vege_id, alias, type in all_aliases:
            if alias: # 確保別名不為空
                candidates.append({
                    'vege_id': vege_id,
                    'alias': alias.strip(),
                    'type': type
                })

        # --- 步驟 2: 準備使用者輸入 (一般及拼音) ---
        pinyin_search_term = "".join(
            [item[0] for item in pinyin(clean_search_term, style=Style.NORMAL)]
        )

        # --- 步驟 3: 進行分層模糊搜尋 ---
        # 3.1: 中文名稱、常見別名、其他學名
        name_candidates = [c for c in candidates if c['type'] in ('中文名稱', '常見別名', '其他學名')]
        name_texts = [c['alias'] for c in name_candidates]
        name_matches_raw = process.extract(
            clean_search_term,
            name_texts,
            scorer=fuzz.ratio,
            limit=15
        )
        good_name_matches = []
        for text, score in name_matches_raw:
            if score >= 80:
                matching_candidates = [c for c in name_candidates if c['alias'] == text]
                for mc in matching_candidates:
                    good_name_matches.append((mc, score, 'name'))

        # 3.2: 羅馬拼音
        pinyin_candidates = [c for c in candidates if c['type'] == '羅馬拼音']
        pinyin_texts = [c['alias'] for c in pinyin_candidates]
        pinyin_matches_raw = process.extract(
            pinyin_search_term,
            pinyin_texts,
            scorer=fuzz.ratio,
            limit=10
        )
        pinyin_matches = []
        for text, score in pinyin_matches_raw:
             if score >= 80:
                matching_candidates = [c for c in pinyin_candidates if c['alias'] == text]
                for mc in matching_candidates:
                    pinyin_matches.append((mc, score, 'pinyin'))

        # 3.3: 錯字
        typo_candidates = [c for c in candidates if c['type'] == '錯字']
        typo_texts = [c['alias'] for c in typo_candidates]
        typo_matches_raw = process.extract(
            clean_search_term,
            typo_texts,
            scorer=fuzz.ratio,
            limit=10
        )
        typo_matches = []
        for text, score in typo_matches_raw:
            if score >= 80:
                matching_candidates = [c for c in typo_candidates if c['alias'] == text]
                for mc in matching_candidates:
                    typo_matches.append((mc, score, 'typo'))

        # --- 步驟 4: 合併、去重、排序 ---
        all_matches = good_name_matches + pinyin_matches + typo_matches

        unique_matches = {}
        for candidate, score, match_type in all_matches:
            vege_id = candidate['vege_id']
            # 如果 vege_id 不在 unique_matches 中，或者當前分數更高，則更新
            if vege_id not in unique_matches or score > unique_matches[vege_id][1]:
                unique_matches[vege_id] = (candidate, score, match_type)

        sorted_matches = sorted(unique_matches.values(), key=lambda x: x[1], reverse=True)[:1]
        
        matched_vege_ids = [match[0]['vege_id'] for match in sorted_matches]

        if not matched_vege_ids:
            return []

        # --- 步驟 5: 獲取匹配蔬菜的詳細資訊 ---
        results_list = []
        # 使用 IN 子句一次性獲取所有需要的資料，提高效率
        # 獲取基本資訊
        query_basic = "SELECT id, vege_name FROM basic_vege WHERE id = ANY(%s);"
        cursor.execute(query_basic, (matched_vege_ids,))
        basic_vege_rows = cursor.fetchall()
        vege_details = {row[0]: {'chinese_name': row[1]} for row in basic_vege_rows}

        # 獲取營養資訊
        query_nutrition = "SELECT * FROM vege_nutrition WHERE vege_id = ANY(%s);"
        cursor.execute(query_nutrition, (matched_vege_ids,))
        nutrition_cols = [desc[0] for desc in cursor.description]
        nutrition_rows = cursor.fetchall()
        for row in nutrition_rows:
            row_dict = dict(zip(nutrition_cols, row))
            veg_id = row_dict['vege_id']
            if veg_id in vege_details:
                vege_details[veg_id]['all_nutrients'] = {k: v for k, v in row_dict.items() if k != 'vege_id'}

        # 獲取別名資訊
        query_aliases = "SELECT vege_id, alias FROM vege_alias WHERE vege_id = ANY(%s) AND type NOT IN ('羅馬拼音', '錯字');"
        cursor.execute(query_aliases, (matched_vege_ids,))
        alias_rows = cursor.fetchall()
        for vege_id, alias in alias_rows:
            if vege_id in vege_details:
                if 'aliases' not in vege_details[vege_id]:
                    vege_details[vege_id]['aliases'] = []
                vege_details[vege_id]['aliases'].append(alias)
        
        # 組合最終結果，並按照模糊搜尋的分數排序
        for vege_id in matched_vege_ids: # 按照排序後的 id 順序來組合
            if vege_id in vege_details:
                detail = vege_details[vege_id]
                results_list.append({
                    'id': vege_id,
                    'chinese_name': detail.get('chinese_name', f"未知蔬菜 (ID: {vege_id})"),
                    'aliases': detail.get('aliases', []),
                    'all_nutrients': detail.get('all_nutrients', {}),
                    'nutrient_name': "總覽",
                    'nutrient_value': None,
                    'unit': ""
                })

        if redis_conn:
            try:
                # 將結果序列化為 JSON 字串並存入 Redis，設定 1 小時 (3600秒) 過期
                # default=str 是為了處理日期時間等無法直接 JSON 序列化的物件
                redis_conn.set(cache_key, json.dumps(results_list, default=str), ex=3600)
                print(f"快取寫入 (SET) - Key: {cache_key}")
            except Exception as e:
                print(f"寫入 Redis 失敗: {e}")


        return results_list
    except Exception as e:
        print(f"Database query failed: {e}")
        return f"資料庫查詢失敗: {e}"
    finally:
        if conn:
            conn.close()