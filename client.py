import socket
import sys
import json


def send (managerHost,managerPort, msg):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(3.0)
    sock.sendto(json.dumps(msg).encode(),(managerHost,int(managerPort)))

    try:
        data, _ = sock.recvfrom(4096)
        print("Reply:", data.decode())
    except socket.timeout:
        print("No reply (timeout)")
    finally:
        sock.close()

if __name__ == "__main__":
    if len(sys.argv)<4 :
        print("Usage:")
        print("  Register user:   py client.py <managerIP> <managerPort> register-user <username> <mport> <cport>")
        print("  Register disk:   py client.py <managerIP> <managerPort> register-disk <diskname> <mport> <cport>")
        print("  Deregister user: py client.py <managerIP> <managerPort> deregister-user <username>")
        print("  Deregister disk: py client.py <managerIP> <managerPort> deregister-disk <diskname>")
        sys.exit(1)

    managerIP,managerPort,option = sys.argv[1],sys.argv[2],sys.argv[3]

    if option == "register-user" and len(sys.argv) == 8:
       msg = {"option": "register-user", "user": sys.argv[4], "address":str(sys.argv[5]) , "mport": int(sys.argv[6]), "cport": int(sys.argv[7])}
    elif option == "register-disk" and len(sys.argv) == 8:
        msg = {"option": "register-disk", "disk": sys.argv[4], "address": str(sys.argv[5]), "mport": int(sys.argv[6]), "cport": int(sys.argv[7]) }
    elif option == "deregister-user" and len(sys.argv) == 5:
        msg = {"option": "deregister-user", "user": sys.argv[4]}
    elif option == "deregister-disk" and len(sys.argv) == 5:
        msg = {"option": "deregister-disk", "disk": sys.argv[4]}
    elif option == "configure-dss" and len(sys.argv) == 8:
        msg = {"option": "configure-dss", "dss": sys.argv[4], "user": sys.argv[5], "num": int(sys.argv[6]), "block_size": int(sys.argv[7])}
    else:
        print("Invalid")
        sys.exit(1)

    send(managerIP,managerPort,msg)