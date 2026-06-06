import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('127.0.0.1', 9001))
    print("Port 9001 is open!")
except Exception as e:
    print("Port 9001 is closed:", e)
finally:
    s.close()
