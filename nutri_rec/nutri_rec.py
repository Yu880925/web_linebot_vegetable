import pandas as pd
import os
import re

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


def get_top_vegetables_by_nutrient(nutrient_name: str,
                                   nutrition_file_path: str = 'veg_data/vege_nutrition_202507211504.xlsx',
                                   basic_vege_file_path: str = 'veg_data/basic_vege_202507211504_good.xlsx',
                                   alias_file_path: str = 'veg_data/vege_alias_202507211504.xlsx'):
    """
    根據指定的營養成分名稱，從Excel檔案中找出含量最高的五項蔬菜。

    Args:
        nutrient_name (str): 營養成分的名稱 (例如: '蛋白質', '維生素C')。
        nutrition_file_path (str): 營養數據Excel檔案的路徑。
        basic_vege_file_path (str): 基本蔬菜資訊Excel檔案的路徑，用於獲取中文名稱。
        alias_file_path (str): 蔬菜別名資訊Excel檔案的路徑，用於獲取別名。

    Returns:
        list: 包含前五項蔬菜詳細資訊的列表，如果找不到營養成分或檔案，則返回錯誤訊息字串。
    """
    if not os.path.exists(nutrition_file_path):
        return f"錯誤：營養數據檔案 '{nutrition_file_path}' 不存在。"
    if not os.path.exists(basic_vege_file_path):
        return f"錯誤：基本蔬菜資訊檔案 '{basic_vege_file_path}' 不存在。"
    if not os.path.exists(alias_file_path):
        return f"錯誤：蔬菜別名檔案 '{alias_file_path}' 不存在。"

    try:
        # 讀取營養數據檔案
        nutrition_df = pd.read_excel(nutrition_file_path)
        # 讀取基本蔬菜資訊檔案
        basic_vege_df = pd.read_excel(basic_vege_file_path)
        # 讀取蔬菜別名檔案
        alias_df = pd.read_excel(alias_file_path)
    except Exception as e:
        return f"錯誤：無法讀取Excel檔案，請確認檔案格式是否正確。錯誤訊息：{e}"

    # 清理所有數據框的欄位名稱 (小寫並移除空白)
    nutrition_df.columns = [col.strip().lower() for col in nutrition_df.columns]
    basic_vege_df.columns = [col.strip().lower() for col in basic_vege_df.columns]
    alias_df.columns = [col.strip().lower() for col in alias_df.columns]

    # 找到 basic_vege_df 中實際的 'vege_id' 和 'vege_name' 欄位
    vege_id_col_basic = None
    chinese_name_col_basic = None
    for col in basic_vege_df.columns:
        if 'vege_id' in col:
            vege_id_col_basic = col
        if 'vege_name' == col: 
            chinese_name_col_basic = col
        elif '中文名稱' in col or 'chinese_name' in col or 'name_cn' in col: 
            chinese_name_col_basic = col
        if vege_id_col_basic and chinese_name_col_basic:
            break

    if not vege_id_col_basic or not chinese_name_col_basic:
        return "錯誤：基本蔬菜資訊檔案中找不到 'vege_id' 或代表中文名稱的欄位。請檢查檔案內容。"

    # 建立 vege_id 到中文名稱的映射字典
    vege_id_to_name = basic_vege_df.set_index(vege_id_col_basic)[chinese_name_col_basic].to_dict()

    # 找到 alias_df 中實際的 'vege_id' 和 'alias' 欄位
    vege_id_col_alias = None
    alias_col_alias = None
    for col in alias_df.columns:
        if 'vege_id' in col:
            vege_id_col_alias = col
        if 'alias' in col: # 假設別名欄位名為 alias
            alias_col_alias = col
        if vege_id_col_alias and alias_col_alias:
            break
    
    if not vege_id_col_alias or not alias_col_alias:
        return "錯誤：蔬菜別名檔案中找不到 'vege_id' 或 'alias' 欄位。請檢查檔案內容。"

    # 建立 vege_id 到別名列表的映射字典
    # 將 alias_df 中的同一 vege_id 的 alias 合併成列表
    vege_id_to_aliases = alias_df.groupby(vege_id_col_alias)[alias_col_alias].apply(list).to_dict()

    df = nutrition_df.copy() # 複製一份用於處理的DataFrame

    # 嘗試透過映射字典獲取對應的英文欄位名稱
    actual_nutrient_column = NUTRIENT_MAPPING.get(nutrient_name) 

    # 將使用者輸入的營養成分名稱也轉換為小寫，以便直接匹配
    input_nutrient_lower = nutrient_name.lower().strip()

    # 確定實際使用的營養成分欄位名稱
    if actual_nutrient_column and actual_nutrient_column in df.columns:
        pass 
    elif input_nutrient_lower in df.columns:
        actual_nutrient_column = input_nutrient_lower
    else:
        return f"錯誤：找不到營養成分 '{nutrient_name}' 的數據。請檢查輸入是否正確或檔案中是否存在該營養成分。"

    # 確保營養成分列是數值類型
    df[actual_nutrient_column] = pd.to_numeric(df[actual_nutrient_column], errors='coerce')
    df.dropna(subset=[actual_nutrient_column], inplace=True) 

    if df.empty:
        return f"找不到 '{actual_nutrient_column}' 的有效數值數據。"

    # 確保 'vege_id' 欄位存在於營養數據中，以便進行查找
    vege_id_col_nutrition = None
    for col in nutrition_df.columns:
        if 'vege_id' in col:
            vege_id_col_nutrition = col
            break
    
    if not vege_id_col_nutrition:
        return "錯誤：營養數據檔案中找不到 'vege_id' 欄位。請檢查檔案內容。"

    # 根據營養成分含量降序排序，取前五項
    top_5_vegetables_df = df.sort_values(by=actual_nutrient_column, ascending=False).head(5)

    # 提取單位 (從 actual_nutrient_column 的後綴，例如 protein_g -> g)
    unit = actual_nutrient_column.split('_')[-1] if '_' in actual_nutrient_column else ''
    
    # 格式化輸出結果為字典列表
    results_list = []
    for index, row in top_5_vegetables_df.iterrows():
        veg_id = row[vege_id_col_nutrition] 
        chinese_name = vege_id_to_name.get(veg_id, f"未知蔬菜 (ID: {veg_id})") 
        aliases = vege_id_to_aliases.get(veg_id, [])
        nutrient_value = row[actual_nutrient_column]
        
        # 獲取所有營養成分數據，去除 vege_id 和其他非營養成分欄位
        all_nutrients_data = {k: v for k, v in row.to_dict().items() if k not in [vege_id_col_nutrition, '蔬菜名稱_原始', '單位_原始', 'vege_name']}
        
        results_list.append({
            "vege_id": veg_id,
            "chinese_name": chinese_name,
            "nutrient_name": nutrient_name, # 查詢的原始營養成分名稱
            "nutrient_value": nutrient_value,
            "unit": unit,
            "aliases": aliases,
            "all_nutrients": all_nutrients_data
        })
    
    return results_list 

def get_vegetables_by_name_or_alias(search_term: str,
                                    nutrition_file_path: str = 'veg_data/vege_nutrition_202507211504.xlsx',
                                    basic_vege_file_path: str = 'veg_data/basic_vege_202507211504_good.xlsx',
                                    alias_file_path: str = 'veg_data/vege_alias_202507211504.xlsx'):
    try:
        nutrition_df = pd.read_excel(nutrition_file_path)
        basic_vege_df = pd.read_excel(basic_vege_file_path)
        alias_df = pd.read_excel(alias_file_path)
    except FileNotFoundError:
        return "錯誤：資料檔案不存在，請確認路徑是否正確。"
    except Exception as e:
        return f"錯誤：讀取 Excel 檔案時發生問題：{e}"

    if 'vege_id' not in nutrition_df.columns or 'vege_id' not in basic_vege_df.columns or 'vege_id' not in alias_df.columns:
        return "錯誤：Excel 檔案中找不到 'vege_id' 欄位。請確認資料結構。"
    if 'vege_name' not in basic_vege_df.columns:
        return "錯誤：Excel 檔案中找不到 'vege_name' 欄位。請確認資料結構。"
    if 'alias' not in alias_df.columns:
        return "錯誤：Excel 檔案中找不到 'alias' 欄位。請確認資料結構。"

    search_term_lower = search_term.lower().strip()
    matched_vege_ids = set()

    # 1. 搜尋 basic_vege_df 中的 vege_name
    direct_matches = basic_vege_df[basic_vege_df['vege_name'].str.lower().str.contains(search_term_lower, na=False)]
    matched_vege_ids.update(direct_matches['vege_id'].tolist())

    # 2. 搜尋 alias_df 中的 alias
    alias_matches = alias_df[alias_df['alias'].str.lower().str.contains(search_term_lower, na=False)]
    matched_vege_ids.update(alias_matches['vege_id'].tolist())

    results_list = []
    if not matched_vege_ids:
        return [] # 沒有找到任何匹配項

    for vege_id in list(matched_vege_ids):
        # 從 nutrition_df 獲取該 vege_id 的所有營養數據
        nutrition_data = nutrition_df[nutrition_df['vege_id'] == vege_id]

        if not nutrition_data.empty:
            row = nutrition_data.iloc[0] # 取第一行數據
            chinese_name = basic_vege_df[basic_vege_df['vege_id'] == vege_id]['vege_name'].iloc[0]
            aliases = alias_df[alias_df['vege_id'] == vege_id]['alias'].tolist()

            all_nutrients = {}
            for col in nutrition_df.columns:
                if col.startswith('vege_id'):
                    continue
                all_nutrients[col] = row[col]

            # 這裡我們不關心特定營養素的名稱和單位，因為是概覽
            # 如果需要顯示某個主要的營養成分，可以自行選擇
            results_list.append({
                'id': vege_id,
                'chinese_name': chinese_name,
                'aliases': aliases,
                'all_nutrients': all_nutrients,
                # 為確保與 get_top_vegetables_by_nutrient 輸出格式一致，添加佔位符
                'nutrient_name': "總覽",
                'nutrient_value': None, # 或設置為某個總覽值
                'unit': ""
            })
    return results_list 