
def windowsMessageBox(title, text, style=0):
    import ctypes   
    MessageBox = ctypes.windll.user32.MessageBoxA   
    return MessageBox(None, text, title, 0x40 | style)

def getkey(key=None):
        key=kbhit()
        if key==True:
            return getch()
        else:
            return key        
        return None
        
try:
    from msvcrt import kbhit, getch
except ImportError:
    import termios, fcntl, sys, os
    def kbhit():
        while True:
            try:
                c = sys.stdin.read(1)
                return c
            except IOError:
                return False 

    def set_term():
        fd = sys.stdin.fileno()
        oldterm = termios.tcgetattr(fd)
        newattr = termios.tcgetattr(fd)
        newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSANOW, newattr)
        oldflags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)
        return oldterm, oldflags
    
    def restore_term(oldterm, oldflags):
        fd = sys.stdin.fileno()
        termios.tcsetattr(fd, termios.TCSAFLUSH, oldterm)
        fcntl.fcntl(fd, fcntl.F_SETFL, oldflags)
        