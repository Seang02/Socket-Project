import socket
import sys
import json
import random
from tools import receiveMSG, clock, blockSize

users = {}
disks = {}
dss = {}

def build_dss_info(name):
    meta = dss[name]
    disk_list = []
    
    for dname in meta["disksOrder"]:
        dmeta = disks[dname]
        disk_list.append({"name": dname,"addr": dmeta["address"],  "cport": dmeta["cport"]})

    return {"dss": name,"num": meta["num"],"block_size": meta["block_size"],"disks": disk_list}

def main():

    if len(sys.argv) != 2:
        print("Incorrect input")
        sys.exit(1)
    
    port = int(sys.argv[1])
    host = "0.0.0.0"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host,port))

    clock("MANAGER"," listening on "+ host + ":"+ str(port))

    while True:
        info, addr = receiveMSG(sock,prefix="MANAGER")
        if info is None:
            continue

        option = info.get("option")

        if option == "register-user":
            name = info.get("user")
            address = info.get("address")
            mport = info.get("mport")
            cport = info.get("cport")

            if name in users:
                reply = {"Status": "Failure", "Reason": "duplicate user"}
            else:
                users[name] = {"addr": address, "mport": mport, "cport":cport}
                reply = {"Status":"Success"}
                clock("MANAGER", "Got message from "+ str(addr)+":"+str(info))

            sock.sendto(json.dumps(reply).encode(), addr)
        
        elif option == "register-disk":
            name = info.get("disk")
            diskAdress = info.get("address")
            mport = info.get("mport")
            cport = info.get("cport")

            if name in disks:
                reply = {"Status": "Failure", "Reason": "Same disks"}
            else:
                disks[name] = {"address": diskAdress, "mport": mport, "cport": cport, "state": "Free"}
                reply = {"Status": "Success"}
                clock("MANAGER", "Registered disk " + str(name) + " (state=Free)")
            
            sock.sendto(json.dumps(reply).encode(), addr)
        
        elif option == "configure-dss":
            dssName = info.get("dss")
            user = info.get("user")
            num = int(info.get("num",0))
            blockS = int(info.get("block_size",0))

            if dssName in dss:
                reply = {"Status": "Failure", "Reason": "The DSS exists"}
            elif num<3:
                reply = {"Status": "Failure", "Reason": "n must be >= 3"}
            elif not blockSize(blockS) or blockS < 128 or blockS > (1024*1024):
                reply = {"Status": "Failure", "Reason": "Must be a power of two"}
            else:
                free = [name for name, meta in disks.items() if meta.get("state") == "Free"]
                if len(free) < num:
                    reply = {"Status": "Failure", "Reason": "insufficient free disks"}
                else:
                    chosen = random.sample(free, num)
                    for d in chosen:
                        disks[d]["state"] = "InDSS"
                        disks[d]["dss"] = dssName

                    dss[dssName] = {"num": num, "block_size": blockS, "disksOrder": chosen, "owner": user, "files": {}}

                    reply = {"Status": "Success", "dss": dssName, "num": num, "block_size": blockS, "disks": chosen}

                    clock("MANAGER", "Configured DSS " + dssName + " with num=" + str(num) +" block_size =" + str(blockS) + " using " + str(chosen))

            sock.sendto(json.dumps(reply).encode(), addr)
        
        elif option =="deregister-user":
            name = info.get("user")

            if name not in users:
                reply = {"Status": "Failure", "Reason": "user not found"}
            
            else:
                del users[name]
                reply = {"Status": "Success"}
                clock("MANAGER", "Deregistered user " + str(name))

            sock.sendto(json.dumps(reply).encode(), addr)
        
        elif option == "deregister-disk":
            name = info.get("disk")
            
            if name not in disks:
                reply = {"Status": "Failure", "Reason": "disk not found"}
            
            else:
                state = disks[name].get("state")
                if state in ("InDSS"):   
                    reply = {"Status": "Failure"}
                else:
                    del disks[name]
                    reply = {"Status": "Success"}
                    clock("MANAGER", "Deregistered disk " + str(name))
            
            sock.sendto(json.dumps(reply).encode(), addr)
        
        elif option == "ls":
            view = {"dss": {}}
            for dname, meta in dss.items():
                view["dss"][dname] = {"num": meta["num"],"block_size": meta["block_size"],"disks": meta["disksOrder"],"files": meta["files"]}

            reply = {"Status": "Success", "dss": view["dss"]}
            sock.sendto(json.dumps(reply).encode(), addr)

        elif option == "copy":
            fname = info.get("file")
            fsize = int(info.get("size", 0))
            owner = info.get("owner")

            if not dss:
                reply = {"Status": "Failure", "Reason": "no DSS configured"}

            else:
                dssName = next(iter(dss))
                dss[dssName]["files"].setdefault(fname, {"size": fsize, "owner": owner})
                reply = {"Status": "Success", "dss_info": build_dss_info(dssName)}
                
            sock.sendto(json.dumps(reply).encode(), addr)

        elif option == "copy-complete":
            dssName = info.get("dss")
            fname = info.get("file")
            fsize = int(info.get("size", 0))
            owner = info.get("owner")

            if dssName not in dss:
                reply = {"Status": "Failure", "Reason": "unknown DSS"}

            else:
                dss[dssName]["files"][fname] = {"size": fsize, "owner": owner}
                reply = {"Status": "Success"}
                clock("MANAGER", "Copy complete for " + fname + " into " + dssName)

            sock.sendto(json.dumps(reply).encode(), addr)

        elif option == "read":
            dssName = info.get("dss")
            fname = info.get("file")
            requester = info.get("user")

            if dssName not in dss:
                reply = {"Status": "Failure", "Reason": "unknown DSS"}

            elif fname not in dss[dssName]["files"]:
                reply = {"Status": "Failure", "Reason": "file not found"}

            else:
                fmeta = dss[dssName]["files"][fname]
                if fmeta.get("owner") != requester:
                    reply = {"Status":"Failure","Reason":"permission denied"}
                else:
                    reply = {"Status": "Success","size": fmeta["size"],"dss_info": build_dss_info(dssName)}
                
            sock.sendto(json.dumps(reply).encode(), addr)

        elif option == "read-complete":
            reply = {"Status": "Success"}
            sock.sendto(json.dumps(reply).encode(), addr)

        elif option == "disk-failure":
            dssName = info.get("dss")
            if dssName not in dss:
                reply = {"Status": "Failure", "Reason": "unknown DSS"}

            else:
                reply = {"Status": "Success", "dss_info": build_dss_info(dssName)}

            sock.sendto(json.dumps(reply).encode(), addr)

        elif option == "recovery-complete":
            reply = {"Status": "Success"}
            sock.sendto(json.dumps(reply).encode(), addr)

        elif option == "decommission-dss":
            dssName = info.get("dss")

            if dssName not in dss:
                reply = {"Status": "Failure", "Reason": "unknown DSS"}

            else:
                for dname in dss[dssName]["disksOrder"]:
                    disks[dname]["state"] = "Free"
                    disks[dname]["dss"] = None
                del dss[dssName]
                reply = {"Status": "Success"}
                clock("MANAGER", "Decommissioned DSS " + str(dssName))

            sock.sendto(json.dumps(reply).encode(), addr)


        
        else:
            clock("MANAGER", "Got unknown command: " + str(info))
        

            

if __name__ == "__main__":
    main()