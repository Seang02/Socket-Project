import socket
import sys
import json
import base64
import threading

from tools import clock, receiveMSG, sendMSG

store = {}
diskName = None
mPort = None
cPort = None

def endcode(b):
    return base64.b64encode(b).decode()

def decode(s):
    return base64.b64decode(s.encode())

def cPort_server(sock):
    clock("[" + diskName + " CPORT]", "listening on 0.0.0.0:" + str(cPort))

    while True:
        try:
            data,addr = sock.recvfrom(65507)
            req = json.loads(data.decode())
            msg = req.get("type")

            if msg == "WRITE_BLOCK":
                key = (req["dss"], req["file"],int(req["stripe"]),int(req["index"]))
                store[key] = {"type": req["block_type"], "bytes": decode(req["data"])}
                sendMSG(sock,addr,{"status": "OK","op":"WRITE_BLOCK"}, prefix="[{} SEND]".format(diskName))

            elif msg == "READ_BLOCK":
                key = (req["dss"], req["file"],int(req["stripe"]),int(req["index"]))
                rec = store.get(key)
                if rec is None:
                    sendMSG(sock, addr, {"status": "ERR", "reason": "missing"},prefix="[{} SEND]".format(diskName))
                else:
                    sendMSG(sock, addr, {
                        "status": "OK", "op": "READ_BLOCK","block_type": rec["type"], "data": endcode(rec["bytes"])}, prefix="[{} SEND]".format(diskName))
                    
            elif msg == "FAIL":
                store.clear()
                sendMSG(sock, addr, {"status": "OK", "op": "FAIL"},prefix="[{} SEND]".format(diskName))
            
            elif msg == "DELETE_ALL":
                store.clear()
                sendMSG(sock, addr, {"status": "OK", "op": "DELETE_ALL"},prefix="[{} SEND]".format(diskName))
            
            else:
                sendMSG(sock, addr, {"status": "ERR", "reason": "unknown"},prefix="[{} SEND]".format(diskName))
        
        except Exception as e:
            clock("[{} CPORT]".format(diskName), "error {}".format(e))

def mPort_server(sock):
    clock("[{} MPORT]".format(diskName), "listening on 0.0.0.0:{}".format(mPort))
    while True:
        try:
            sock.recvfrom(2048)
        except Exception as e:
            clock("[{} MPORT]".format(diskName), "error {}".format(e))

def thread(func, *args):
    t = threading.Thread(target=func, args=args)
    t.daemon = True
    t.start()
    return t


def main():
    global diskName,mPort,cPort

    if len(sys.argv) != 6:
        print("Python Disk.py <disk name>,<manager ip>,<manager port>,<m port>,<c port>")
        sys.exit(1)

    diskName = sys.argv[1]
    managerIP = sys.argv[2]
    managerPORT = int(sys.argv[3])
    mPort = int(sys.argv[4])
    cPort = int(sys.argv[5])

    m_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m_sock.bind(("0.0.0.0", mPort))
    c_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c_sock.bind(("0.0.0.0", cPort))

    thread(mPort_server, m_sock)
    thread(cPort_server, c_sock)

    clock("[{}]".format(diskName), "ready.")
    threading.Event().wait()

if __name__ == "__main__":
    main()





