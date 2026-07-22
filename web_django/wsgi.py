"""
WSGI config for web_django project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""


import os
# Nhập hàm 'get_wsgi_application' từ thư viện Django 
from django.core.wsgi import get_wsgi_application
# Thiết lập biến môi trường 'DJANGO_SETTINGS_MODULE'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_django.settings')
# Khởi tạo đối tượng ứng dụng và gán vào biến 'application'
application = get_wsgi_application()