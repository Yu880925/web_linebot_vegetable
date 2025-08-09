import os
from linebot import LineBotApi
from linebot.v3.messaging.models import RichMenuArea, RichMenuBounds, MessageAction, RichMenuSize # 移除 RichMenu
from dotenv import load_dotenv
from linebot.v3.messaging.api.messaging_api import MessagingApi
from linebot.v3.messaging.api.messaging_api_blob import MessagingApiBlob
from linebot.v3.messaging.models import RichMenuRequest
from linebot.v3.messaging.api_client import ApiClient, Configuration

load_dotenv()

# 從環境變數中獲取 Channel Access Token
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', 'YOUR_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET', 'YOUR_CHANNEL_SECRET') # app.py 會用到

# 創建 Configuration 實例
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

# 創建 ApiClient 實例
api_client = ApiClient(configuration)

# 創建 MessagingApi 實例
messaging_api = MessagingApi(api_client) # 修正這裡
# 創建 MessagingApiBlob 實例
messaging_api_blob = MessagingApiBlob(api_client) # 修正這裡

def create_and_upload_rich_menu():
    # 首先刪除所有現有的富選單
    try:
        rich_menus = messaging_api.get_rich_menu_list().rich_menus
        if rich_menus:
            print("正在刪除現有的富選單...")
            for rich_menu_info in rich_menus:
                messaging_api.delete_rich_menu(rich_menu_info.rich_menu_id)
                print(f"已刪除富選單: {rich_menu_info.rich_menu_id}")
        else:
            print("沒有找到現有的富選單。")
    except Exception as e:
        print(f"刪除現有富選單時發生錯誤: {e}")

    # 2. 創建 Rich Menu
    try:
        # 使用新的 MessagingApi 來創建 Rich Menu，並將 rich_menu_body 包裝在 RichMenuRequest 中
        rich_menu_id = messaging_api.create_rich_menu(
            RichMenuRequest(
                size=RichMenuSize(width=2500, height=843),
                no_action=False,
                name="Main_Menu",
                chat_bar_text="選單",
                selected=True,
                areas=[
                    RichMenuArea(
                        bounds=RichMenuBounds(x=0, y=0, width=833, height=843),
                        action=MessageAction(text="上傳圖片")
                    ),
                    RichMenuArea(
                        bounds=RichMenuBounds(x=833, y=0, width=833, height=843),
                        action=MessageAction(text="輸入營養成分")
                    ),
                    RichMenuArea(
                        bounds=RichMenuBounds(x=1666, y=0, width=834, height=843),
                        action=MessageAction(text="輸入現有食材")
                    )
                ]
            )
        )
        # 從返回的 RichMenuIdResponse 物件中提取 rich_menu_id 字串
        rich_menu_id_str = rich_menu_id.rich_menu_id # 修正這裡
        print(f"成功創建 Rich Menu, ID: {rich_menu_id_str}")

        # 3. 上傳 Rich Menu 圖片
        image_path = "richmenu_vege.jpg"
        if not os.path.exists(image_path):
            print(f"錯誤: 圖片檔案不存在於 {image_path}")
            return

        with open(image_path, "rb") as f:
            image_bytes = f.read() # 讀取圖片內容為位元組流

        # 根據圖片副檔名判斷 content_type
        file_extension = os.path.splitext(image_path)[1].lower()
        if file_extension == ".png":
            content_type = "image/png"
        elif file_extension == ".jpeg" or file_extension == ".jpg":
            content_type = "image/jpeg"
        else:
            print(f"錯誤: 不支援的圖片格式 {file_extension}")
            return

        # 設定 HTTP 標頭
        headers = {
            "Content-Type": content_type
        }

        # 使用新的 MessagingApiBlob 來上傳圖片，傳遞 rich_menu_id 和圖片位元組流，並設定 _headers
        messaging_api_blob.set_rich_menu_image(
            rich_menu_id_str,      # rich_menu_id (字串型別)
            image_bytes,           # 圖片位元組流
            _headers=headers       # 新增這裡，直接設定 HTTP 標頭
        )
        print("成功上傳 Rich Menu 圖片")

        # 4. 將 Rich Menu 設定為預設
        # 使用 v3 MessagingApi 的 set_default_rich_menu
        messaging_api.set_default_rich_menu(rich_menu_id_str) # 這裡也使用字串 ID
        print("成功設定預設 Rich Menu")

    except Exception as e:
        print(f"創建/上傳 Rich Menu 時發生錯誤: {e}")

if __name__ == "__main__":
    create_and_upload_rich_menu() 