import socket
import threading

def handle_client(client_sock):
    try:
        client_sock.settimeout(10)
        data = client_sock.recv(8192)
        if not data:
            return

        client_sock.settimeout(None)

        # 1. Парсим первую строку запроса
        first_line = data.split(b'\r\n')[0].decode('utf-8', errors='ignore')
        parts = first_line.split()
        if len(parts) < 2:
            return

        method = parts[0].upper()
        url = parts[1]

        # 🔥 ИГНОРИРУЕМ HTTPS (CONNECT) ЗАПРОСЫ
        if method == 'CONNECT':
            client_sock.close()
            return

        # 2. Определяем хост, порт и путь
        host, port, path = '', 80, '/'
        
        if url.startswith('http://'):
            # Браузер передал полный URL
            url_part = url[7:]  # убираем http://
            if '/' in url_part:
                host_port, path = url_part.split('/', 1)
                path = '/' + path
            else:
                host_port = url_part
                
            if ':' in host_port:
                host, port = host_port.split(':')
                port = int(port)
            else:
                host = host_port
        else:
            # Браузер передал только путь, ищем Host в заголовках
            path = url
            for line in data.split(b'\r\n'):
                if line.lower().startswith(b'host:'):
                    host_header = line[5:].decode('utf-8', errors='ignore').strip()
                    if ':' in host_header:
                        host, port = host_header.split(':')
                        port = int(port)
                    else:
                        host = host_header
                    break

        if not host:
            return

        # 🔥 ИГНОРИРУЕМ ФОНОВЫЕ ЗАПРОСЫ БРАУЗЕРА (опционально)
        ignore_hosts = ['telemetry.mozilla.org', 'accounts.firefox.com', 'fastly-edge.com', 'mozilla.org']
        if any(h in host for h in ignore_hosts):
            client_sock.close()
            return

        # 3. Формируем запрос для целевого сервера
        new_request = f"{method} {path} HTTP/1.1\r\n"
        for line in data.split(b'\r\n')[1:]:
            if line and not line.lower().startswith(b'host:') and not line.lower().startswith(b'connection:'):
                new_request += line.decode('utf-8', errors='ignore') + '\r\n'
        new_request += f"Host: {host}\r\n"
        new_request += "Connection: close\r\n\r\n"

        # 4. Подключаемся к целевому серверу
        target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target.settimeout(15)
        target.connect((host, port))
        target.sendall(new_request.encode('utf-8'))

        # 5. Получаем ответ и сразу пересылаем клиенту
        response_headers = b''
        while b'\r\n\r\n' not in response_headers:
            chunk = target.recv(8192)
            if not chunk:
                break
            response_headers += chunk
            client_sock.sendall(chunk)

        # 6. ЛОГИРОВАНИЕ
        try:
            status_line = response_headers.split(b'\r\n')[0].decode('utf-8', errors='ignore')
            code_reason = " ".join(status_line.split()[1:]) if len(status_line.split()) > 1 else "???"
            port_str = f':{port}' if port != 80 else ''
            print(f"http://{host}{port_str}{path} - {code_reason}")
        except Exception:
            pass

        # 7. Досылаем оставшееся тело (для стримов)
        target.settimeout(None)
        while True:
            chunk = target.recv(8192)
            if not chunk:
                break
            client_sock.sendall(chunk)

        target.close()

    except Exception as e:
        print(f"ОШИБКА: {e}")
    finally:
        client_sock.close()

# ================= ЗАПУСК СЕРВЕРА =================
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('127.0.0.1', 8080))
server.listen(5)

print("=" * 50)
print("ПРОКСИ СЕРВЕР ЗАПУЩЕН: http://127.0.0.1:8080")
print("Настройте браузер и открывайте сайты.")
print("=" * 50)

try:
    while True:
        client, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client,), daemon=True)
        t.start()
except KeyboardInterrupt:
    print("\nЗавершение работы...")
    server.close()
