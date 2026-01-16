# Non-blocking terminal keypress reader
# Dan Jackson, 2023

# spell-checker:ignore kbhit getch tcgetattr tcsetattr TCSADRAIN

import sys
if sys.platform == 'win32':
    from msvcrt import kbhit, getch
else:
    import select
    import tty
    import termios
    import sys

class KeyReader:
    """
    Non-blocking terminal keypress reader
    Dan Jackson, 2023
    """

    def __init__(self, verbose = False):
        self.verbose = verbose
    
    def __del__(self):
        self.close()
    
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, type, value, tb):
        self.close()
    
    def open(self):
        if self.verbose: print("KeyReader: Opening...")
        if sys.platform != 'win32': # 'darwin' / 'linux'
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
    
    def close(self):
        if self.verbose: print("KeyReader: Closing...")
        if sys.platform != 'win32': # 'darwin' / 'linux'
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
    
    def read(self):
        #if self.verbose: print("KeyReader: Read...")
        value = None
        if sys.platform == 'win32':
            if kbhit():
                value = getch().decode('utf-8')
        else: # 'darwin' / 'linux'
            select_result = select.select([sys.stdin], [], [], 0)
            if sys.stdin in select_result[0]:
                value = sys.stdin.read(1)
        return value
    
# Example code if run from command-line
if __name__ == "__main__":
    import time
    with KeyReader(verbose=True) as key_reader:
        while True:
            value = key_reader.read()
            if value is not None:
                print("Key: " + value)
            else:
                time.sleep(0.050)
#except Exception as e:
#    print('Exception ' + e.__doc__ + ' -- ' + e.message)
