FROM postgres:14

# 安裝 pgvector extension
RUN apt-get update && \
    apt-get install -y git build-essential postgresql-server-dev-14 && \
    git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git && \
    cd pgvector && \
    make && make install && \
    cd .. && rm -rf pgvector && \
    apt-get remove -y git build-essential postgresql-server-dev-14 && \
    apt-get autoremove -y && \
    apt-get clean

# 可選：切換回預設工作目錄
WORKDIR /var/lib/postgresql