#!/usr/bin/python3

import os
import signal
import sys
import time
import zmq
import logging.handlers

curDir = os.path.abspath(os.path.dirname(__file__))
logPath = os.path.join(curDir, "log", "restart.log")
trace = logging.getLogger()
trace.setLevel(logging.DEBUG)
formatter = logging.Formatter(fmt="%(asctime)s %(filename)s[line:%(lineno)d]%(levelname)s - %(message)s",
                                  datefmt="%m/%d/%Y %I:%M:%S %p")
file_handler = logging.handlers.TimedRotatingFileHandler(logPath, when='d', interval=5, backupCount=10)
file_handler.suffix = "%Y-%m-%d.log"
file_handler.setFormatter(formatter)  # 可以通过setFormatter指定输出格式
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
console.setFormatter(formatter)
trace.addHandler(console)
trace.addHandler(file_handler)
trace.info('hello')
trace.info('%s'%logPath)

class Restart():
    def __init__(self):
        super(Restart, self).__init__()

        #self.trace = trace
    def check_connect(self):
        try:
            context = zmq.Context(); 
            socket = context.socket(zmq.REQ); socket.connect('tcp://127.0.0.1:7651')
            socket.send_json({'req': { 'command': 'hi', 'device': 'd'}})
        
            if socket.recv_json() == {'rep': {'device': 'd', 'id': None, 'result': 'hi'}}:
                context.destroy()
                return True
            else:
                context.destroy()
                return False
        except:
            return False

    def run(self):
        start_time=time.time()
        trace.info('hello restart.py')
        time.sleep(20)
        while 1:
            heart_time=time.time()
            if heart_time-start_time>=600:
                start_time=time.time()
                trace.info('heart_beat 10min')
            time.sleep(10)
            if self.check_connect() == False:
                if self.kill_target('daemon.py')==True:
                    os.system('/usr/bin/python3 %s/daemon.py &'%curDir) 
                    trace.info('daemon.py restart.....')
 
    def get_now_time(self):
        # 获取当前的本地时间
        now_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
        return now_time
 
    def kill(self,pid):
        trace.info('pid',pid)
        # pgid=os.getpgid(pid)
        # print(pgid)
        # a = os.killpg(pgid,signal.SIGKILL)
        try:
            a = os.kill(pid,signal.SIGKILL)
            trace.info('已杀死pid为%s的进程,　返回值是:%s' % (pid, a))
            return True
        except:
            trace.info('No such process')
            return False
 
    def kill_target(self,target):
        cmd_run="ps aux | grep {}".format(target)
        out=os.popen(cmd_run).read()
        for line in out.splitlines():
            if '/usr/bin/python3' in line:
                trace.info(line)
                pid = int(line.split()[1])
                if self.kill(pid) ==True:
                    return True
                else:
                    return False
        return False

def main():    
    rs=Restart()
    rs.run()               
     
if __name__ == '__main__':
    main()
         

            
