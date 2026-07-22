"""
ASGI config for web_django project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
# Nhập hàm để khởi tạo ứng dụng theo chuẩn ASGI
from django.core.asgi import get_asgi_application

# Thiết lập file settings mặc định cho dự án
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_django.settings')

# Khởi tạo biến application để chạy ứng dụng trên các server hỗ trợ ASGI (như Daphne hoặc Uvicorn)
application = get_asgi_application()