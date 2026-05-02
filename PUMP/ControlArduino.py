

for one in ports:
    portsList.append(str(one))
    print(str(one))

com= input("Select port: ")

for i in range(len(portsList)):
    if portsList[i].startswith("COM"+str(com)):
        use = "COM"+str(com)
        print(use)

serialInst.baudrate = 9600
serialInst.port = use
serialInst.open()  

while True:
    command = input("Arduino Command (ON/OFF/FeedRate/exit):")
    serialInst.write(command.encode("utf-8"))

    if command == "exit":
        exit()

    response = serialInst.readline().decode("utf-8").strip()
    if response:
        print(f"Arduino: {response}")
