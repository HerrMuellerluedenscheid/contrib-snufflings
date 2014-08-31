#/usr/bin/python 
import socket
import threading
import struct
import hashlib
import threading 
import time
from pyrocko import util


class SnufflingSocket(threading.Thread):
    def __init__(self, action=None):
        threading.Thread.__init__(self)
        self.PORT = 9876
        self.clients = []
        self.action = action
        self._stop_server = False

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


    def handle(self, s, addr, stop_event):
        data = s.recv(1024)
        s.send(self.create_handshake_resp(data))
        lock = threading.Lock()

        while not stop_event.is_set():
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

    def run(self):
        print 'starting server'
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', self.PORT))
        s.listen(1)
        self.stop_thread = threading.Event()
        while 1:# and not self._stop_server:
            conn, addr = s.accept()
            print 'Connected by', addr
            self.clients.append(conn)
            self.server_thread = threading.Thread(target = self.handle, args = (conn, addr, self.stop_thread)).start()

    def join(self):
        print 'stopping server'
        self.stop_thread.set()
        self.server_thread.join()

    def update_action(self, data):
        print 'updating'
        #TESTING::::::::::
        #self.server_thread.join()
        data = data[:-1]
        #data = data.replace(",",".")
        print data
        print type(data)
        #data = float(data)
        print data
        #data = str(data).split('.')[0]
        #t = util.str_to_time(data,format='%Y-%m-%d %H:%M:%S.FRAC')
        #print t
        self.action(data)
        time.sleep(1.)

    #clients = []
    #start_server()
