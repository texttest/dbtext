
from threading import Thread
import time

class PipeReaderThread(Thread):
    def __init__(self, proc, ready_text, filename=None):
        Thread.__init__(self)
        self.proc = proc
        self.ready_bytes = ready_text.encode()
        self.ready_line = None
        self.logfile = open(filename, "wb") if filename else None
        
    def run(self):
        while self.proc.poll() is None:
            line = self.proc.stdout.readline()
            if self.ready_line is None and self.ready_bytes in line:
                self.ready_line = line.decode().strip()
            if self.logfile and not self.logfile.closed:
                self.logfile.write(line)
                self.logfile.flush()
                
    def wait_for_text(self):
        while self.ready_line is None:
            time.sleep(0.1)
        return self.ready_line
    
    def terminate(self):
        if self.logfile:
            self.logfile.close()
        self.proc.terminate()
        self.join()

