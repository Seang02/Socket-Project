def clock(tag,msg):
    import time
    now = time.strftime("%H:%M:%S")
    print(tag +" " +"Time:" + now +"" + msg)

def sendMSG(sock, addr, info, prefix="SEND"):
    import json
    data = json.dumps(info).encode()
    sock.sendto(data,addr)
    clock(prefix," " + str(addr) +" "+ str(info))

def receiveMSG(sock, prefix="RECEIVED"):
    import json

    data, addr = sock.recvfrom(65507)
    text = data.decode()
    info = json.loads(text)
    clock(prefix, ":" + str(addr) +""+ str(info))
    return info, addr

def blockSize(x: int) -> bool:
    return x > 0 and (x & (x-1)) == 0

    
