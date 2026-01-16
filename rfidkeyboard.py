# Non-blocking raw-input reader for enter-terminated time-batched numeric input
# (e.g. M301 Mifare Card RF ID Reader)
# Dan Jackson, 2020-2021

# spell-checker:ignore Mifare SCANCODES Numpad Minux, SETFL, GETFL, NONBLOCK

from __future__ import print_function   # Python 2 support for:  print(..., end=...)
import sys                              # Python 2 doesn't support print(..., flush=True)
import time
import os
import fcntl

# QWERTY layout 
SCANCODES = {
    0x01: "\x1b", # Escape
    0x02: "1", 0x03: "2", 0x04: "3", 0x05: "4", 0x06: "5", 0x07: "6", 0x08: "7", 0x09: "8", 0x0A: "9", 0x0B: "0", 
    0x0C: "-", 0x0D: "=", 
    0x0E: "\b", # Backspace
    0x0F: "\t", # Tab
    0x10: "q", 0x11: "w", 0x12: "e", 0x13: "r", 0x14: "t", 0x15: "y", 0x16: "u", 0x17: "i", 0x18: "o", 0x19: "p", 0x1A: "[", 0x1B: "]", 
    0x1C: "\n", # Enter
    #0x1D: "{Left-Control}", 
    0x1E: "a", 0x1F: "s", 0x20: "d", 0x21: "f", 0x22: "g", 0x23: "h", 0x24: "j", 0x25: "k", 0x26: "l", 0x27: ";", 0x28: "\'", 
    0x29: "`", # Key left of "1"
    #0x2A: "{Left-Shift}", 
    0x2B: "#", # "#" left of inset Enter key on UK layout; "\" above enter (after "]") on US layout
    0x2C: "z", 0x2D: "x", 0x2E: "c", 0x2F: "v", 0x30: "b", 0x31: "n", 0x32: "m", 0x33: ",", 0x34: ".", 0x35: "/", 
    #0x36: "{Right-Shift}", 
    0x37: "*", # Numpad-Multiply
    #0x38: "{Left-Alt}", 
    0x39: " ", # Space
    #0x3A: "{Caps-Lock}",
    #0x3B: "{F1}", 0x3C: "{F2}", 0x3D: "{F3}", 0x3E: "{F4}", 0x3F: "{F5}", 0x40: "{F6}", 0x41: "{F7}", 0x42: "{F8}", 0x43: "{F9}", 0x44: "{F10}", 
    #0x45: "{Num Lock}", 
    #0x46: "{Scroll Lock}",
    ### Numpad Home/Up/Page Up/Minux/Left/Center/Right/Plus/End/Down/Page Down/Ins/Del
    0x47: "7", 0x48: "8", 0x49: "9", 0x4A: "-", 0x4B: "4", 0x4C: "5", 0x4D: "6", 0x4E: "+", 0x4F: "1", 0x50: "2", 0x51: "3", 0x52: "0", 0x53: ".",
    0x56: "\\", # Key left of "Z" on UK layout
    #0x57: "{F11}", 0x58: "{F12}", 
    0x60: "\n", # Numpad-Enter
    #0x61: "{Right-Control}", 
    0x62: "/", # Numpad-Divide
    #0x63: "{Print Screen}", 0x64: "{Right-alt}", 0x66: "{Home}", 0x67: "{Up}", 0x68: "{Page Up}", 0x69: "{Left}", 0x6A: "{Right}", 0x6B: "{End}", 0x6C: "{Down}", 0x6D: "{Page Down}", 0x6E: "{Insert}", 0x6F: "{Delete}", 0x77: "{Pause}", 0x7d: "{Super/Windows}", 0x7f: "{Context menu}",
}

class RfidReader:
    """
        Non-blocking raw-input reader for enter-terminated time-batched numeric input
        (e.g. M301 Mifare Card RF ID Reader)
        Dan Jackson, 2020-2021
    """

    def __init__(self, deviceName = None, verbose = False, deviceIndex = None):
        # Ensure device name is a list of allowed devices
        if deviceName is None or deviceName == "":
            self.deviceName = []
        elif isinstance(deviceName, list):
            self.deviceName = deviceName
        else:
            self.deviceName = [deviceName]
        self.verbose = verbose          # Noisy output to stdout for debugging
        self.deviceIndex = deviceIndex  # None/0=(Default) last matching device name found, 1=1st matching, ...
        self.file = None
        self.card = ""
        self.input = ""
        self.last = None
    
    def __del__(self):
        self.close()
    
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, type, value, tb):
        self.close()
    
    def open(self):
        print("RfidReader: Opening..." + str(self.deviceName))
        inputDeviceBase = "/sys/class/input/"
        inputPathBase = "/dev/input/"
        inputDevice = None
        matchIndex = 0
        for device in os.listdir(inputDeviceBase):
            if not device.startswith("event"):
                continue
            nameFile = inputDeviceBase + device + "/device/name"
            with open(nameFile, 'r') as nf:
                name = nf.read().strip()
            print("RfidReader: Checking input [" + device + "]: '" + name + "'")
            if len(self.deviceName) > 0 and name not in self.deviceName:
                continue
            matchIndex += 1
            print("RfidReader: ...match " + str(matchIndex) + ", looking for " + str(self.deviceIndex) + "")
            if self.deviceIndex is not None and self.deviceIndex > 0 and matchIndex != self.deviceIndex:
                continue
            inputDevice = inputPathBase + device
        if inputDevice == None:
            print("RfidReader: Cannot find a matching input device: " + str(self.deviceName))
            raise Exception("Cannot find matching input device")
        print("RfidReader: Found input device: " + inputDevice)
        self.file = open(inputDevice, "rb", buffering=0)
        # Non-blocking mode
        fd = self.file.fileno()
        fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)
    
    def close(self):
        if self.file == None:
            return
        #print("RfidReader: Closing...")
        self.file.close()
        self.file = None
    
    def read(self):
        #print("RfidReader: Read...")
        self.card = ""
        now = time.time()
        if (self.input != "" and self.last != None and now - self.last > 2):
            print("RfidReader: Input timeout")
            self.input = ""
            self.last = None
        while True:
            eventData = None
            try:
                eventData = self.file.read(24)
            except IOError as e:
                if e.errno == 11: # Python 2 gets [Errno 11] Resource temporarily unavailable
                    if self.verbose:
                        print("!", end="") # flush=True (can't with Python 2 __future__ print)
                        sys.stdout.flush()
                    break
                raise

            if eventData is None: # Python 3 get no event
                if self.verbose:
                    print(".", end="") # flush=True (can't with Python 2 __future__ print)
                    sys.stdout.flush()
                #raise TypeError("No data read")
                break

            self.last = now 

            #timeS: eventData.readUInt32LE(0),
            #timeUS: eventData.readUInt32LE(4),
            #type: eventData.readUInt16LE(8),
            #code: eventData.readUInt16LE(10),
            #value: eventData.readInt32LE(12),

            # 28=Enter, 2='1', 3='2', ..., 10='9', 11='0'
            code = eventData[10]
            # 0=release, 1=press, 2=repeat
            value = eventData[12]

            # Compatibility with Python 2
            if isinstance(code, str):
                code = ord(code)
            if isinstance(value, str):
                value = ord(value)

            # Map scan code to character
            char = SCANCODES.get(code)
            charCode = 0
            if char is not None and len(char) == 1:
                charCode = ord(char)

            if value == 1: # pressed
                if char is not None and self.verbose:
                    print("<" +  str(code) + "=" + hex(code) + "," + str(charCode) + "=" + hex(charCode) + "," + char.replace("\n", "\\n").replace("\b", "\\b").replace("\t", "\\t").replace("\x1b", "\\x1b") + ">", end="") # flush=True (can't with Python 2 __future__ print)
                    sys.stdout.flush()
                if (char == "\n"):                    # Keycode for enter
                    self.card = self.input
                    self.input = ""
                elif char is not None:      # Keycode for decimal digit: 2='1', 3='2', ..., 10='9', 11='0'
                    self.input = self.input + char
                else:
                    # Unhandled scan code
                    if self.verbose:
                        print("[?" + str(code) + "=" + hex(code) + "]", end="") # flush=True (can't with Python 2 __future__ print)
                        sys.stdout.flush()
                    pass
        
        # No card found / cards exist
        if self.card == "":
            return None
        return self.card
        
# Example code if run from command-line
if __name__ == "__main__":
    # Default device name (None=last to enumerate), override as first command-line parameter
    deviceName = None
    #deviceName = "RPI Wired Keyboard 1"
    if len(sys.argv) > 1: deviceName = sys.argv[1]
    print("Example using device: " + str(deviceName))
    
    with RfidReader(deviceName, verbose=True) as rfid:
        while True:
            card = rfid.read()
            if card is not None:
                print("CARD: " + card)
            time.sleep(0.050)
        
#except Exception as e:
#    print('Exception ' + e.__doc__ + ' -- ' + e.message)

