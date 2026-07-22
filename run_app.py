import webview
import threading
import subprocess
import sys
import time
import urllib.request
import urllib.error

SERVER_URL = "http://127.0.0.1:8000"
server_proc = None

def run_django():
    """Khởi động Django development server trong một tiến trình con.
    Dùng `sys.executable` để đảm bảo dùng chính Python của môi trường hiện tại.
    """
    global server_proc
    python = sys.executable or "python"
    cmd = [python, "manage.py", "runserver", "--noreload"]
    try:
        server_proc = subprocess.Popen(cmd)
        server_proc.wait()
    except Exception as e:
        print("Lỗi khi chạy Django:", e)

def wait_for_server(url, timeout=30):
    """Chờ server trả lời HTTP trong khoảng `timeout` giây."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if getattr(resp, 'status', None) in (200, 301, 302, None):
                    return True
        except Exception:
            time.sleep(0.5)
    return False

def stop_server():
    global server_proc
    if server_proc and server_proc.poll() is None:
        try:
            server_proc.terminate()
            server_proc.wait(5)
        except Exception:
            try:
                server_proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    t = threading.Thread(target=run_django, daemon=True)
    t.start()

    print("Đang khởi động N1-Jewelry App...")
    if wait_for_server(SERVER_URL, timeout=30):
        print("Server đã sẵn sàng.")
    else:
        print("Server chưa trả lời sau 30s — vẫn cố gắng mở cửa sổ.")

    try:
        webview.create_window(
            'N1 JEWELRY - PHẦN MỀM QUẢN LÝ TRANG SỨC',
            SERVER_URL,
            width=1200,
            height=800,
            resizable=True
        )
        webview.start()
    finally:
        stop_server()
        print("Server đã dừng.")