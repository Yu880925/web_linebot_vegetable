FROM python:3.10-slim-bullseye


WORKDIR /app

# 安裝 python3-venv 以建立虛擬環境
RUN apt-get update && apt-get install -y python3-venv && rm -rf /var/lib/apt/lists/*

# 建立虛擬環境
RUN python3 -m venv /opt/venv

# 複製 requirements.txt
COPY requirements.txt .

# 使用虛擬環境的 pip 安裝套件
RUN /opt/venv/bin/pip install --upgrade pip
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# 複製程式碼資料夾
COPY rec_veg /app/rec_veg/
COPY nutri_rec /app/nutri_rec/
COPY . .

# 將虛擬環境加入 PATH，之後執行 python 就是用虛擬環境的
ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 5000

CMD ["python", "app.py"]
