import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('127.0.0.1', 8000))
    print("Port 8000 is open!")
except Exception as e:
    print("Port 8000 is closed:", e)
finally:
    s.close()
