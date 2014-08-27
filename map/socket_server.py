#/usr/bin/python 
import socket
import threading
import struct
import hashlib


class SnufflingSocket():
    def __init__(self, action=None):
        self.PORT = 9876
        self.clients = []
        self.action = action

    def create_handshake_resp(self, handshake):
        final_line = ""
        lines = handshake.splitlines()
        for line in lines:
            parts = line.partition(": ")
            print parts
            if parts[0] == "Sec-WebSocket-Key1":
                key1 = parts[2]
            elif parts[0] == "Sec-WebSocket-Key2":
                key2 = parts[2]
            elif parts[0] == "Host":
                host = parts[2]
            elif parts[0] == "Origin":
                origin = parts[2]
            final_line = line

        spaces1 = key1.count(" ")
        spaces2 = key2.count(" ")
        num1 = int("".join([c for c in key1 if c.isdigit()])) / spaces1
        num2 = int("".join([c for c in key2 if c.isdigit()])) / spaces2

        token = hashlib.md5(struct.pack('>II8s', num1, num2, final_line)).digest()

        return (
            "HTTP/1.1 101 WebSocket Protocol Handshake\r\n"
            "Upgrade: WebSocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Origin: %s\r\n"
            "Sec-WebSocket-Location: ws://%s/\r\n"
            "\r\n"
            "%s") % (
            origin, host, token)


    def handle(self, s, addr):
        data = s.recv(1024)
        s.send(self.create_handshake_resp(data))
        lock = threading.Lock()

        while 1:
            print "Waiting for data from", s, addr
            data = s.recv(1024)
            print "Done"
            if not data:
                print "No data"
                break

            print 'Data from', addr, ':', data
            if self.action:
                self.update_action(data)
            # Broadcast received data to all clients
            lock.acquire()
            [conn.send(data) for conn in self.clients]
            lock.release()

        print 'Client closed:', addr
        lock.acquire()
        self.clients.remove(s)
        lock.release()
        s.close()

    def start_server(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', self.PORT))
        s.listen(1)
        while 1:
            conn, addr = s.accept()
            print 'Connected by', addr
            self.clients.append(conn)
            threading.Thread(target = self.handle, args = (conn, addr)).start()

    def update_action(self, data):
        self.action(data)

    #clients = []
    #start_server()
