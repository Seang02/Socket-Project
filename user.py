import socket
import sys
import threading
import json
import os
import base64
import random

from tools import clock

managerHost = None
managerPort = None
user = None
mPort = None
cPort = None

def sendManager(msg,timeout=3.0):
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0",0))
    sock.settimeout(timeout)

    try:
        sock.sendto(json.dumps(msg).encode(),(managerHost,managerPort))
        data,addr = sock.recvfrom(65507)
        return json.loads(data.decode())
    
    except socket.timeout:
        return {"Status":"Failure","Reason":"timeout"}
    
    finally:
        sock.close()

def byteString(blocks):
    if not blocks:
        return b""
    
    out = bytearray(blocks[0])
    
    for b in blocks[1:]:
        for i, val in enumerate(b):
            out[i] ^= val
    
    return bytes(out)

def diskIndex(n,index):
    out = n-((index%n)+1)

    return out

def writeBlock(disk,payload):
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.settimeout(2.0)

    try:
        addr = (disk["addr"],disk["cport"])
        sock.sendto(json.dumps(payload).encode(),addr)
        data,addr = sock.recvfrom(65507)
        return json.loads(data.decode())
    
    except socket.timeout:
        return {"status": "ERR", "reason": "timeout"}
    
    finally:
        sock.close()

def readBlock(disk,payload):
    return writeBlock(disk,payload)

def sendFail(disk):
    return writeBlock(disk, {"type": "FAIL"})

def deleteAll(disk):
    return writeBlock(disk, {"type": "DELETE_ALL"})

def copyFile(path,dss):
    info = dss["block_size"]
    num = dss["num"]
    disks = dss["disks"]
    name = os.path.basename(path)
    size = os.path.getsize(path)

    with open(path,"rb") as f:
        numStr = (size + (num - 1) * info - 1) // ((num - 1) * info)

        for i in range(numStr):
            dataBlocks = []
            
            for _ in range(num - 1):
                chunk = f.read(info)
                chunk = (chunk or b"").ljust(info, b"\x00")
                dataBlocks.append(chunk)
        
            combine = byteString(dataBlocks)
            blockIndex = diskIndex(num,i)

            data_iter = iter(dataBlocks)
            blocks = [("parity", combine) if i == blockIndex else ("data", next(data_iter))for i in range(num)]

            for k, (btype, bb) in enumerate(blocks):
                payload = {"type": "WRITE_BLOCK","dss": dss["dss"],"file": name,"stripe": i,"index": k,"block_type": btype, "data": base64.b64encode(bb).decode()}
                writeBlock(disks[k], payload)

def readFile(dss,name,outPath,size,error):
    blockSize = dss["block_size"]
    num = dss["num"]
    disks = dss["disks"]
    numStr = (size+(num-1)*blockSize-1)//((num-1)*blockSize)

    def once(index):
        results = [None]*num
        threads = []

        def separate(j):
            payload = {"type": "READ_BLOCK","dss": dss["dss"],"file": name,"stripe": index,"index": j}
            results[j] = readBlock(disks[j],payload)

        for j in range(num):
         t = threading.Thread(target=separate,args=(j,))
         t.start()
         threads.append(t)

        for t in threads:
             t.join()

        blocks=[]

        for j in range(num):
            r = results[j]

            if r and r.get("status") == "OK":
                bb = base64.b64decode(r["data"])

                if random.randint(0,99) < error and len(bb) > 0:
                    bArray = bytearray(bb)
                    prob = random.randint(0,len(bArray)-1)
                    bArray[prob] ^= 0x01
                    bb = bytes(bArray)

                blocks.append((r["block_type"],bb))

            else:
                blocks.append((None,None))
        
        return blocks
    
    with open(outPath,"wb") as out:
        for index in range(numStr):
            while True:
                blocks = once(index)
                if any(bt is None for (bt, _) in blocks):
                    continue

                pindex = diskIndex(num, index)

                data_bytes = [bb for j, (bt, bb) in enumerate(blocks) if j != pindex]
                parity_ok = (blocks[pindex][0] == "parity" and blocks[pindex][1] == byteString(data_bytes))

                if parity_ok:
                    for j, (bt, bb) in enumerate(blocks):
                        if j != pindex:
                            out.write(bb)
                    break
    
    with open(outPath,"rb+") as out:
        out.truncate(size)

def failAndrecover(dss):
    num = dss["num"]
    disks = dss["disks"]
    failIndex = random.randint(0, num - 1)
    failed = disks[failIndex]
    clock("[USER]", "Failing disk {}".format(failed["name"]))
    sendFail(failed)

    ls = sendManager({"option":"ls"})
    files = []
    dssName = dss["dss"]

    for k, meta in ls.get("dss",{}).items():
        if k == dssName:
            for fname,finfo in meta["files"].items():
                files.append((fname,finfo["size"]))
    
    blockSize = dss["block_size"]

    for fname, size in files:
        numStr = (size + (num - 1) * blockSize - 1) // ((num - 1) * blockSize)
        
        for strIndex in range(numStr):
            valid = []

            for j, d in enumerate(disks):
                if j == failIndex:
                    continue

                r = readBlock(d,{"type": "READ_BLOCK","dss": dssName,"file": fname,"stripe": strIndex,"index": j})

                if r.get("status") == "OK":
                    valid.append((j, r["block_type"], base64.b64decode(r["data"])))
            
            rbytes = byteString([bb for (_i, _t, bb) in valid])
            pindex = diskIndex(num, strIndex)
            btype = "parity" if failIndex == pindex else "data"

            writeBlock(failed, {"type": "WRITE_BLOCK","dss": dssName,"file": fname,"stripe": strIndex,"index": failIndex,"block_type": btype,"data": base64.b64encode(rbytes).decode()})

def function():
    print("Usage:")
    print("  python User.py <manager_ip> <manager_port> <user_name> <m_port> <c_port>")
    print("Commands:")
    print("  register")
    print("  configure <dss> <n> <block_size>")
    print("  copy <dss> <path/to/file>")
    print("  read <dss> <file_name> <out_path> <p_error_percent>")
    print("  ls")
    print("  disk-failure <dss>")
    print("  decommission <dss>")
    print("  deregister")
    print("  quit")

def main():
    global managerHost,managerPort,user,mPort,cPort

    if len(sys.argv) != 6:
        function()
        sys.exit(1)

    managerHost = sys.argv[1]
    managerPort = int(sys.argv[2])
    user        = sys.argv[3]
    mPort       = int(sys.argv[4])
    cPort       = int(sys.argv[5])

    print("User {} ready. Type commands.".format(user))

    while True:
        try:
            parts = input("> ").strip().split()
        except EOFError:
            break
        if not parts:
            continue

        choice = parts[0]

        if choice == "quit":
            break

        elif choice == "register":
            print(sendManager({"option": "register-user","user": user,"address": managerHost,"mport": mPort,"cport": cPort}))
        
        elif choice == "configure":
            if len(parts) != 4:
                print("usage: configure <dss> <n> <block_size>")
                continue
            dssName = parts[1]
            num = int(parts[2])
            blockSize = int(parts[3])
            print(sendManager({"option": "configure-dss","dss": dssName,"user": user,"num": num,"block_size": blockSize }))

        elif choice == "ls":
            print(sendManager({"option": "ls"}))
        
        elif choice == "copy":
            if len(parts) != 3:
                print("usage: copy <dss> <path/to/file>")
                continue

            path = parts[2]
            if not os.path.exists(path):
                print({"Status": "Failure", "Reason": "file not found"})
                continue

            size = os.path.getsize(path)

            r = sendManager({"option": "copy","file": os.path.basename(path),"size": size,"owner": user})

            if r.get("Status") != "Success":
                print(r)
                continue

            dssInfo = r["dss_info"]

            copyFile(path, dssInfo)

            print(sendManager({"option": "copy-complete","dss": dssInfo["dss"],"file": os.path.basename(path),"size": size,"owner": user}))

        elif choice == "read":
            if len(parts) != 5:
                print("usage: read <dss> <file_name> <out_path> <p_error_percent>")
                continue

            dssName = parts[1]
            fname = parts[2]
            outPath = parts[3]
            p = int(parts[4])

            r = sendManager({"option": "read","dss": dssName,"file": fname,"user": user})

            if r.get("Status") != "Success":
                print(r)
                continue

            dssInfo = r["dss_info"]
            size = r["size"]

            readFile(dssInfo, fname, outPath, size, p)
            print(sendManager({"option": "read-complete","dss": dssName,"file": fname,"user": user}))

        elif choice == "disk-failure":
            if len(parts) != 2:
                print("usage: disk-failure <dss>")
                continue

            dssName = parts[1]

            r = sendManager({"option": "disk-failure", "dss": dssName})

            if r.get("Status") != "Success":
                print(r)
                continue

            dssInfo = r["dss_info"]
            failAndrecover(dssInfo)
            print(sendManager({"option": "recovery-complete", "dss": dssName}))
        
        elif choice == "decommission":
            if len(parts) != 2:
                print("usage: decommission <dss>")
                continue

            dssName = parts[1]

            print(sendManager({"option": "decommission-dss", "dss": dssName}))

        elif choice == "deregister":
            print(sendManager({"option": "deregister-user", "user": user}))

        else:
            print("Unknown")

if __name__ == "__main__":
    main()


        


