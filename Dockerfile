# 智能投标助手 —— 部署镜像（Azure Container Apps）
# 纯 Python 服务：FastAPI + uvicorn。包在 src/ 下，靠 PYTHONPATH=src 导入（无 pip 安装）。
# .doc 解析仅走 Azure Content Understanding（CU_ENDPOINT），镜像内不含本地转换器。
FROM python:3.14-slim

# 不写 .pyc、日志不缓冲（容器日志实时可见）
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# 先装依赖（单独一层，利用构建缓存：requirements 不变则不重装）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 再拷源码与前端静态资源（main.py 用 src/web 提供 /static 与页面）
COPY src/ ./src/

# Container Apps 通过 ingress targetPort 路由到此端口；用 $PORT 兼容平台注入，缺省 8080
ENV PORT=8080
EXPOSE 8080

# 以非 root 运行（安全基线）
RUN useradd -m appuser
USER appuser

# 启动 FastAPI 应用（单进程；Container Apps 靠多副本水平扩展，不在容器内开多 worker）
CMD ["sh", "-c", "uvicorn bid_copilot.api.main:app --host 0.0.0.0 --port ${PORT}"]
