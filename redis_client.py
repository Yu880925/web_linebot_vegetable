# redis_client.py (修改後)
import os
import redis
import redis.exceptions

def get_redis_connection():
    """
    從環境變數中取得 Redis 連線設定，並返回一個 Redis 連線物件。
    優先使用 REDIS_URL，如果沒有則使用 REDIS_HOST 和 REDIS_PORT。
    """
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        try:
            # 從 URL 直接建立連線
            r = redis.from_url(redis_url, decode_responses=True)
            r.ping()
            print(f"成功透過 REDIS_URL 連線到 Redis 伺服器")
            return r
        except redis.exceptions.ConnectionError as e:
            print(f"無法透過 REDIS_URL 連線到 Redis 伺服器")
            print(f"錯誤訊息: {e}")
            return None
    else:
        # 維持舊的 host/port 連線方式
        redis_host = os.environ.get('REDIS_HOST', 'localhost')
        redis_port = int(os.environ.get('REDIS_PORT', 6379))
        try:
            r = redis.StrictRedis(
                host=redis_host,
                port=redis_port,
                db=0,
                decode_responses=True
            )
            r.ping()
            print(f"成功連線到 Redis 伺服器：{redis_host}:{redis_port}")
            return r
        except redis.exceptions.ConnectionError as e:
            print(f"無法連線到 Redis 伺服器：{redis_host}:{redis_port}")
            print(f"錯誤訊息: {e}")
            return None