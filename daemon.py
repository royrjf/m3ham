#!/usr/bin/python3

import sys
import os
import time
import socket
import threading
import traceback
from rcomm import Rcomm
from serv import Serv
from queue import LifoQueue
from crc import custom_crc32
import crcmod.predefined
from YModem import YModem
import platform
from binascii import a2b_hex
from utils import bstr2int
import copy
import crcmod
import struct
import logging
import logging.handlers
import json
import rstserial
import random
import jsonConfig
import rstserial
curDir = os.path.abspath(os.path.dirname(__file__))
logPath = os.path.join(curDir, "log", "ham.log")
#binPath = os.path.join(curDir, "d.bin")
trace = logging.getLogger()
trace.setLevel(logging.DEBUG)
formatter = logging.Formatter(fmt="%(asctime)s %(filename)s[line:%(lineno)d]%(levelname)s - %(message)s",
                                  datefmt="%m/%d/%Y %I:%M:%S %p")
#file_handler = logging.FileHandler("daemon.log")
#file_handler = logging.handlers.TimedRotatingFileHandler("/home/ruijunfeng/works/fusion/d2ham/log/daemon.log", when='d', interval=1, backupCount=90)
file_handler = logging.handlers.TimedRotatingFileHandler(logPath, when='d', interval=1, backupCount=15)
file_handler.suffix = "%Y-%m-%d.log"
file_handler.setFormatter(formatter)  # 可以通过setFormatter指定输出格式
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
console.setFormatter(formatter)
trace.addHandler(console)
trace.addHandler(file_handler)
trace.info('hello')
trace.info('%s'%logPath)
__VERSION__ = '0.1'

class Daemon( threading.Thread ):

    def __init__(self):
        super(Daemon, self).__init__()
        self._stop_event = threading.Event()
   
        self.res_cache = {} # format: {"id": {"res": {}, "time": 1234}, "id2":...}
        self.res_cache_timeout = 5
        self.crc_func = crcmod.mkCrcFun(0x11021, rev=False, initCrc=0x0000, xorOut=0x0000)
        self.cup_run_state =['IDLE','RUN','DELAY','STOP','TIMEOUT','REVERSE']
        self.cup_state =['READY','WAIT','SUCCESS']
    def join(self, timeout=1):
        self._stop_event.set()
        self.rcomm.join()
        self.serv.join()
        self.checkcom.join()
        self._stop_event.set()
        super(Daemon, self).join(timeout)
    
    def run(self): 
        self.init_rcomm()
        self.init_serv()
        #while self.process_close_door()== False:
        #    time.sleep(0.2)
        for i in range(0,3):
            time.sleep(0.2)
            if self.m3_lattice_close_all_led() == True:
                break;
        trace.info('hello beans_control')
        while not self._stop_event.is_set():
            time.sleep(0.5)

    def init_rcomm(self):
        self.rcomm = Rcomm(trace)
        self.rcomm.start()
    
    def init_serv(self):
        self.serv = Serv(trace, gui_port=7651)
        self.serv.process_gui_hook = self._process_gui_hook
        self.serv.start()
    
    def _process_gui_hook(self, gui_sock):
        try:
            data = gui_sock.recv_json()
            trace.info('gui msg: %s' %(data))
            self.process_gui_json(gui_sock, data)
        except Exception as ex:
            #trace.error(traceback.format_exc(sys.exc_info()[-1]))
            trace.error('failed to process json: %s' % (ex))
            gui_sock.send_json({})
            return False
    def process_gui_json(self, gui_sock, data):
        req = data.get('req', False)
        if req is False:
            gui_sock.send_json({})
            return
        device = req.get('device', False)
        if device is False:
            trace.warning('failed to get device')
            gui_sock.send_json({})
            return
        rev = getattr(self, 'process_device_%s' % (device))(req)
        trace.debug('send_json -> %s' % str(rev))
        gui_sock.send_json(rev)
    def process_device_m3(self, data):
        cmd = data.get('command', False)
        if cmd is False:
            return {}
        if cmd=='hi':
            return {'rep': {'device':'m3', 'result':'hi'}}
            
        elif cmd == 'beans_board_hi':
            rev=self.beans_board_hi()
            if rev == True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
                
        elif cmd == 'ac_poll':
            self.rcomm.dev_send(
                self.rcomm.dev_comb.AC, b'\x5a\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xd2')
            try:
                data = self.rcomm.dev_comb.AC.q.get(timeout=0.2)
                #trace.info('data--->%s'%data)
            except:
                #self.rcomm.open_dev()
                rstserial.RstSerial(1) 
                return {'rep': {'device': 'd', 'result': 'error', 'error_level': 'warning', 'meta':'no ack'}}

            if len(data) != 18:
                return {'rep': {'device': 'd', 'result': 'error'}}
            else:
                return {'rep': {'device':'d', 'result': 'success', 't': (data[4]<<8|data[3])/10, 'h':(data[7]<<8|data[6])/10}}
        elif cmd =='read_ac_register':
            address=data.get('address',False)
            if address is False:
                return self.set_res_cache(id_, {'rep': {'device':'d', 'result':'error'}})
            try:
                address=int(address)
                address=address.to_bytes(1,'big')
            except:
                trace.error('address invalid: %s' %address)
                return self.set_res_cache(id_, {'rep': {'device':'d', 'result':'error'}})   
            cmd=b'\x5a\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00%c\x00\x00\x00' %(address)   
            crc8 = crcmod.predefined.Crc('crc-8-maxim')
            crc8.update(cmd)
            c=crc8.crcValue.to_bytes(1,'big')
            cmd=cmd+c
            trace.info('%s' %cmd) 
            try:
                self.rcomm.dev_send(self.rcomm.dev_comb.AC, cmd)
                data= self.rcomm.dev_comb.AC.q.get(timeout=2)
                ac_register_data =data[14]
                return {'rep': {'device':'d', 'result': 'success', 'data':'%s' %ac_register_data}}
            except:
                return {'rep': {'device': 'm3', 'result': 'error'}}    
        elif cmd =='write_ac_register':
            address=data.get('address',False)
            if address is False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            num=data.get('data',False)
            if num is False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            try:
                address=int(address).to_bytes(1,'big')
                num=int(num).to_bytes(1,'big')
            except:
                trace.error('address invalid: %s' %address)
                return {'rep': {'device': 'd', 'result': 'error'}}   
            cmd=b'\x5a\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00%c%c\x00\x00' %(address,num)   
            crc8 = crcmod.predefined.Crc('crc-8-maxim')
            crc8.update(cmd)
            c=crc8.crcValue.to_bytes(1,'big')
            cmd=cmd+c
            trace.info('%s' %cmd)     
            try:
                self.rcomm.dev_send(self.rcomm.dev_comb.AC, cmd)
                return {'rep': {'device': 'm3', 'result': 'success'}}
            except:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='hi_pcb':
            board=data.get('board',False)
            if board==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            if board =='lattice':
                command='lH'
            if board == 'beans':
                command='OH'
            command = command.encode('latin-1')
            crc = struct.pack('H', self.crc_func(command))
            command+= crc    
            trace.info('%s' %command)
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, command)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
            except:
                trace.error('no ack')
                return {'rep': {'device': 'm3', 'result': 'error'}}
            return {'rep': {'device': 'm3', 'result': 'success'}}
        elif cmd =='pcb_version':
            rev=self.m3_pcb_version(data)
            if rev==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            else:
                return {'rep': {'device': 'm3', 'result': rev}}
        elif cmd =="led_flash_start":
            self.beans_board_hi(retry=100)
            rev=self.process_led_flash_start()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}} 
        elif cmd =="led_flash_stop":
            rev=self.process_led_flash_stop()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}} 
        elif cmd =="lattice_led_control":
            rev=self.m3_lattice_led_control(data)
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}                
        elif cmd =="lattice_led_clear":
            rev=self.m3_lattice_led_clear()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =="xl9535_driver":
            para_list=data.get('para')
            board=data.get('board')
            if board=='lattice':
                board_addr='l'
            if board=='beans':
                board_addr='O'
            xl9535_addr=chr(int(data.get('xl9535_addr')))
            rev=self.m3_gen_frame(board_addr,'x',xl9535_addr,'%c%c'%(para_list[0],para_list[1]))
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =="xl9535_set":
            para_list=data.get('para')
            board=data.get('board')
            if board=='lattice':
                board_addr='l'
            if board=='beans':
                board_addr='O'
            xl9535_addr=chr(int(data.get('xl9535_addr')))
            rev=self.m3_gen_frame(board_addr,'X',xl9535_addr,'%c%c'%(para_list[0],para_list[1]))
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='xl9535_read':
            board=data.get('board')
            if board=='lattice':
                board_addr='l'
            if board=='beans':
                board_addr='O'
            rev=self.m3_gen_frame(board_addr,'Y',chr(1),'')
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='read_sensor':
            ch=data.get('ch',False)
            if ch ==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            rev=self.process_read_sensor(ch)
            if rev == False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'success','meta': rev }}
        elif cmd =="lattice_sensor":
            devAddr=data.get('devAddr')
            rev=self.m3_lattice_gen_frame(devAddr,'i','')
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =="lock":
            lock_ids,lock_ids_str=self.m3_lattile_lock_driver_process(data)
            self.m3_lattice_gen_frame('d',lock_ids)
            retry=3
            time.sleep(0.1)
            for i in range(0,retry):
                rev=self.process_read_sensor(lock_ids_str)
                if list(rev.values()).count('CLOSE')==0:
                    return {'rep': {'device': 'm3', 'result': 'success'}}
                time.sleep(0.1)
            return {'rep': {'device': 'm3', 'result': 'error','meta':rev}}
        elif cmd =="lattice_close_all_led":
            rev=self.m3_lattice_close_all_led()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='query_lucky_key':
            cmd='OQ'
            cmd = cmd.encode('latin-1')
            crc = struct.pack('H', self.crc_func(cmd))
            cmd+= crc
            trace.info('%s' %cmd)
            retry=3
            for i in range(0,retry):
                self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
                try:
                    r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                    r=r.decode('latin-1')
                    trace.debug('r -> %s' %r)
                    if r.startswith('OQ'):
                        r=r.split(',')
                        if r[1] == '1':
                            press_state='true'
                        else:
                            press_state='false'
                        return {'rep': {'device': 'm3', 'result': 'success','count':r[2],'press':press_state}}
                except:
                    trace.error('no ack')
                    return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='clear_lucky_key':
            cmd='Ok'
            cmd = cmd.encode('latin-1')
            crc = struct.pack('H', self.crc_func(cmd))
            cmd+= crc
            trace.info('%s' %cmd)
            retry=3
            for i in range(0,retry):
                self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
                try:
                    r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                    trace.debug('r -> %s' %r)
                    if r.startswith(b'Ok'):
                        return {'rep': {'device': 'm3', 'result': 'success'}}
                except:
                    trace.error('no ack')
                    return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd == 'open_lid':
            rev=self.process_open_lid(data)
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd == 'close_lid':
            rev=self.process_close_lid(data)
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='lid_control':
            rev=self.m3_lid_control_process(data)
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='lid_poll':  
            rev=self.m3_lid_poll_process(data)
            if rev==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'success','mate':rev}}
        elif cmd == 'drop_beans_poll':
            ch=data.get('ch',False)
            if ch== False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            circle=data.get('circle',False)
            if circle ==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            command='Od%c'%(int(ch)-1)
            command = command.encode('latin-1')
            crc = struct.pack('H', self.crc_func(command))
            command+= crc    
            trace.info('%s' %command)
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, command)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                r=r.decode('latin-1')
                if r.startswith('Oderr'):
                    return {'rep': {'device': 'm3', 'result': 'error'}}
                elif r.startswith('Od'):
                    r_list=r.split(',')
                    return {'rep': {'device': 'm3', 'result': 'success','ch':ch,'circle':r_list[1]}}
                else:
                    return {'rep': {'device': 'm3', 'result': 'error'}}
            except:
                trace.error('no ack')
                return {'rep': {'device': 'm3', 'result': 'error'}}
                
        elif cmd =='drop_beans':
            ch=data.get('ch',False)
            if ch==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            circle=data.get('circle',False)
            if circle==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            command=''
            if int(ch)>7 or int(ch)<1:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            if int(circle)>20:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            command='OD%c%c%c'%(1,int(ch),int(circle))
            trace.info('command-->%s'%command)  
            command = command.encode('latin-1')
            crc = struct.pack('H', self.crc_func(command))
            command+= crc
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, command)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=1.5*int(circle))
                r=r.decode('latin-1')
                if r.startswith('ODbusy'):
                    return {'rep': {'device': 'm3', 'result': 'error'}}
                elif r.startswith('ODok'):
                    return {'rep': {'device': 'm3', 'result': 'success'}}
                else:
                    return {'rep': {'device': 'm3', 'result': 'error'}}
            except:
                trace.error('no ack')
                return {'rep': {'device': 'm3', 'result': 'error'}}
            return {'rep': {'device': 'm3', 'result': 'success'}}
        elif cmd =='open_door':
            rev=self.process_open_door()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='close_door':
            rev=self.process_close_door()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd=='lighting_on':
            rev=self.process_uv_on()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd=='lighting_off':
            rev=self.process_uv_off()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd=='uv_on':
            rev=self.process_uv_on()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd=='uv_off':
            rev=self.process_uv_off()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd =='close_door':
            command=b'kP1\x03\x1f\xc4'
            try:
                self.rcomm.dev_send(self.rcomm.dev_comb.Y, command)
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'kP'):
                    return {'rep': {'device': 'm3', 'result': 'success'}}
            except:
                trace.error('no ack')
                return {'rep': {'device': 'm3', 'result': 'error'}}
            return {'rep': {'device': 'm3', 'result': 'success'}}
        elif cmd == 'read_cup_ss':
            rev =self.process_read_cup_ss()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'success'}}
        elif cmd == 'cup_forward':
            duty=data.get('duty',False)
            if duty == False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            delay=data.get('delay',False)#10ms
            if delay == False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            rev=self.cup_forward(int(duty),int(delay))
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd == 'cup_backward':
            duty=data.get('duty',False)
            if duty == False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            timeout=data.get('timeout',False)#10ms
            if delay == False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            rev=self.cup_forward(int(duty),int(timeout))
            rev=self.cup_backward(duty,timeout)
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}
        elif cmd == 'read_cup_state':
            rev=self.read_cup_state()
            if rev==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'success','meta':rev}}
        elif cmd == 'read_cup_run_state':
            rev=self.read_cup_run_state()
            if rev==False:
                return {'rep': {'device': 'm3', 'result': 'error'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'success','meta':rev}}
        elif cmd == 'drop_cup':
            rev=self.read_cup_run_state()
            if rev != 'IDLE':
                time.sleep(3)
                trace.info('cup is busy???,cup state:%s' %rev)
                rev=self.cup_state_clear()
                if rev == False:
                    trace.info('cup is busy???,cup state:%s' %rev)
                    return {'rep': {'device': 'm3', 'result': 'error'}}
            rev=self.push_cup()
            if rev==True:
                return {'rep': {'device': 'm3', 'result': 'success'}}
            else:
                return {'rep': {'device': 'm3', 'result': 'error'}}

    def process_write_ACregister(self,address,t,cabinet):
        num=int(cabinet)-1
        data_temp=t
        ac_register_data=0
        try:
            address=address.to_bytes(1,'big')
            t=int(t).to_bytes(1,'big')
        except:
            trace.error('address invalid: %s' %address)
            return False
        cmd=b'\x5a\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00%c%c\x00\x00' %(address,t)   
        crc8 = crcmod.predefined.Crc('crc-8-maxim')
        crc8.update(cmd)
        c=crc8.crcValue.to_bytes(1,'big')
        cmd=cmd+c
        trace.info('%s' %cmd)     
        try:
            self.rcomm.dev_send(self.rcomm.dev_comb.__dict__[self.ac[num]], cmd)
            time.sleep(0.05)
            cmd=b'\x5a\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00%c\x00\x00\x00' %(address)       
            crc8 = crcmod.predefined.Crc('crc-8-maxim')
            crc8.update(cmd)
            c=crc8.crcValue.to_bytes(1,'big')
            cmd=cmd+c
            try:
                self.rcomm.dev_send(self.rcomm.dev_comb.__dict__[self.ac[num]], cmd)
                t_list= self.rcomm.dev_comb.__dict__[self.ac[num]].q.get(timeout=2)
                if len(t_list)!=18:
                    return False
                ac_register_data =t_list[14]
                if ac_register_data==data_temp:
                    return True
                else:
                    return False
            except:
                return False
        except:
            return False            
    def process_read_ACregister(self,address,cabinet):
        num=int(cabinet)-1
        cmd=b'\x5a\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00%c\x00\x00\x00' %(address)       
        crc8 = crcmod.predefined.Crc('crc-8-maxim')
        crc8.update(cmd)
        c=crc8.crcValue.to_bytes(1,'big')
        cmd=cmd+c
        try:
            self.rcomm.dev_send(self.rcomm.dev_comb.__dict__[self.ac[num]], cmd)
            t_list= self.rcomm.dev_comb.__dict__[self.ac[num]].q.get(timeout=2)
            if len(t_list)!=18:
                return -1
            ac_register_data =t_list[14]
            return ac_register_data
        except:
            return -1

    def get_res_cache(self, id_):
        return self.res_cache.get(id_, {}).get("res", None)

    def set_res_cache(self, id_, res):
        if id_ != "":
            res["rep"]["id"] = id_
        # remove the timeout cache
        item=self.res_cache.items()
        
        for cache_id in list(self.res_cache):
            cache_res=self.res_cache[cache_id]
            try:
                if time.time() - cache_res["time"] > self.res_cache_timeout:
                    del self.res_cache[cache_id]
            except:
                pass
        self.res_cache[id_] = {"res": res, "time": time.time()}
        return res
        
    def process_rst_serial(self,data):
        CMD_BIT=1
        STATE_BIT=2
        SUM_BIT=3
        cmd_list=[0x53,0x01,0x02,0x56]
        serial_id=data.get('serial_id',False)
        if serial_id==False:
            return False
        state=data.get('state',False)
        if state==False:
            return False
        cmd_list[CMD_BIT]=int(serial_id)
        if state=="OFF":
            cmd_list[STATE_BIT]=1
        else:
            cmd_list[STATE_BIT]=2
        cmd_list[SUM_BIT]=cmd_list[0]+cmd_list[1]+cmd_list[2]
        cmd_list=list(map(chr,cmd_list))
        for i in range(0,4):
            cmd+=cmd_list[i]
        cmd=cmd.encode('latin-1')    
    def process_reset_serial(self,ch):
        rev=rstserial.RstSerial(int(ch))
        return rev
    def m3_lattice_led_control(self,data,retry=3):
        colour=data.get('colour',False)
        if colour==False:
            return False
        led_ids=data.get('led_ids',False)
        if led_ids==False:
            return False
        led_list=led_ids.split(',')
        if led_list.count('205') ==1:
            led_num=len(led_list)+2
        else:
            led_num=len(led_list)
        cmd='lw'+chr(45)+chr(led_num)+chr(colour[0])+chr(colour[1])+chr(colour[2])
        for d in led_list:
            if int(d) in range(101,105):#1~4
                cmd=cmd+chr(int(d)-100)
            elif int(d) in range(105,108):#8~10
                cmd=cmd+chr(int(d)-100+3)
            elif int(d) in range(201,205):#11~14
                cmd=cmd+chr(19-(int(d)-200))
            elif int(d) in range(205,206):#5~7
                cmd=cmd+chr(5)+chr(6)+chr(7)
            elif int(d) in range(206,210):#14~18
                cmd=cmd+chr(20-(int(d)-200))
            elif int(d) in range(301,313):#19~30
                cmd=cmd+chr(int(d)-300+18)
            elif int(d) in range(401,416):#31~45
                cmd=cmd+chr(46-(int(d)-400))
            else:
                return False
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'lLED'):
                    return True
            except:
                trace.error('no ack')
                return False
        return False
    def m3_lattice_led_control_old(self,data,retry=3):
        colour=data.get('colour',False)
        if colour==False:
            return False
        led_ids=data.get('led_ids',False)
        if led_ids==False:
            return False
        led_list=led_ids.split(',')
        cmd_id=3
        cmd='l'+chr(cmd_id)+chr(43)+chr(len(led_list))+chr(colour[0])+chr(colour[1])+chr(colour[2])
        for d in led_list:
            if int(d) in range(101,108):#1~7
                cmd=cmd+chr(int(d)-100)
            elif int(d) in range(201,209):#8~15
                cmd=cmd+chr(16-(int(d)-200))
            elif int(d) in range(301,313):#16~28
                cmd=cmd+chr(int(d)-300+15)
            elif int(d) in range(401,416):#29~43
                cmd=cmd+chr(43-(int(d)-400))
            else:
                return False
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'lLED'):
                    return True
            except:
                trace.error('no ack')
                return False
        return False
    def m3_lattice_led_clear(self,retry=3):
        cmd='l'+chr(6)
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'lCLEAR'):
                    return True
            except:
                trace.error('no ack')
                return False
        return False
    def m3_lattice_close_all_led(self,retry=3):
        cmd='lg'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'lgok'):
                    return True
            except:
                trace.error('no ack')
                return False
        return False
    def m3_lattile_lock_driver_process(self,data):
        lock_ids=data.get('lock_id',False)
        if lock_ids ==False:
            return False
        lock_list=list(map(int,lock_ids.split(',')))
        if len(lock_list)>2:
            return False
        if 205 in lock_list:
            lock_num=len(lock_list)+1
        else:
            lock_num=len(lock_list)
        lock_para=chr(lock_num)
        para=''
        para_str=''
        for d in lock_list:
            if d//100 == 1: #10 8 12 15
                para=chr(d%100)
                para_str+=str(d%100)
            elif d//100 == 2:
                d=7+d%100
                if d == 12: #this cabinet has two lock
                    para=chr(12)+chr(13)
                    para_str+=str(12)+','+str(13)
                elif d >12:
                    para=chr(d+1)
                    para_str+=str(d+1)
                else:
                    para=chr(d)
                    para_str+=str(d)
            elif d//100 == 3:
                para=chr(17+d%100)
                para_str+=str(17+d%100)
            elif d//100 == 4:
                para=chr(29+d%100)
                para_str+=str(29+d%100)
            else:
                return False
            #d=(d//100-1)*16+d%100
            para_str+=','
            lock_para=lock_para+para 
        trace.info('para_str-->%s'%para_str)
        return lock_para,para_str[0:-1]
    def m3_gen_frame(self,board_addr,command,xl9535_addr,para,retry=2):
        cmd=board_addr+command+xl9535_addr+para
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'%s%sok' %(board_addr.encode(),command.encode())):
                    return True
                else:
                    trace.error('error ack')
            except:
                trace.error('no ack')
                return False
        return False
    def m3_lid_control_process(self,data,retry=3):
        ch_list=data.get('ch',False)
        if ch_list==False:
            return False
        ch_len=len(ch_list) 
        cmd='OC%c'%ch_len
        back_duty=90
        wait_time=10
        for d in range(0,ch_len):
            cmd+=chr(int(ch_list[d]))
            cmd+=chr(back_duty)
            cmd+=chr(wait_time)
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'OC'):
                    return True
            except:
                trace.error('no ack')
                return False
        return False
    def m3_lid_poll_process(self,data,retry=3):
        cmd='OS'
        
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                r=r.decode('latin-1')
                trace.debug('r -> %s' %r)
                if r.startswith('OS'):
                    return r[3]
            except:
                trace.error('no ack')
                return False
        return False
    def cup_forward(self,duty=4,delay=10,retry=3):
        #cmd='OP'+chr(int(duty))+chr(delay_list[0])+chr(delay_list[1])
        cmd='Og'+chr(int(4))+chr(delay)+chr(10)
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=20)
                r=r.decode('latin-1')
                trace.debug('r -> %s' %r)
                if r.startswith('Og'):
                    return True
            except:
                trace.error('no ack')
                return False
        return False
    def cup_backward(self,duty=4,timeout=40,retry=3):
        cmd='OG'+chr(int(duty))+chr(timeout)
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=20)
                r=r.decode('latin-1')
                trace.debug('r -> %s' %r)
                if r.startswith('OG'):
                    return True
            except:
                trace.error('no ack')
                return False
        return False
    def read_cup_run_state(self,retry=3):
        cmd='Oj'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=20)
                r=r.decode('latin-1')
                trace.debug('r -> %s' %r)
                if r.startswith('Oj'):
                    r_list=r.split(',')
                    state=self.cup_run_state[int(r_list[1])]
                    return state
            except:
                trace.error('no ack')
                return False
        return False
    def read_cup_state(self,retry=3):
        cmd='OJ'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=20)
                r=r.decode('latin-1')
                trace.debug('r -> %s' %r)
                if r.startswith('OJ'):
                    r_list=r.split(',')
                    state=self.cup_state[int(r_list[1])]
                    return state
            except:
                trace.error('no ack')
                return False
        return False
    def m3_drop_cup(self,data,retry=3):
        delay_list=data.get('delay')
        duty=data.get('duty')
        #cmd='OP'+chr(int(duty))+chr(delay_list[0])+chr(delay_list[1])
        cmd='OP'+chr(int(4))+chr(10)+chr(10)
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=20)
                r=r.decode('latin-1')
                trace.debug('r -> %s' %r)
                if r.startswith('OP'):
                    return True
            except:
                trace.error('no ack')
                return False
        return False
    def push_cup(self,retry=2):
        for i in range(0,retry):
            rev=self.cup_forward(duty=4,delay=40)
            trace.info('cup_forward start')
            if rev == True:
                start_time=time.time()
                while 1:
                    cur_time=time.time()
                    if(cur_time-start_time>10):
                        trace.info('cup_forward timeout')
                        time.sleep(0.5)
                        break
                    time.sleep(0.2)
                    if self.read_cup_run_state() == 'IDLE':
                        state=self.read_cup_state()
                        if state == 'SUCCESS':
                            trace.info('state-->%s'%state)
                            return True
                        else:
                            break
            else:
                trace.info('cup_forward return error')
                return False
            
            time.sleep(1)
            
            rev=self.cup_backward(duty=4,timeout=40)
            if rev == True:
                trace.info('cup_backward start')
                start_time=time.time()
                while self.read_cup_run_state() != 'IDLE':
                    cur_time=time.time()
                    if(cur_time-start_time>10):
                        trace.info('cup_backward timeout')
                        time.sleep(0.5)
                        break
                    trace.info('backward wait idle')
                    time.sleep(0.2)
            else:
                trace.info('cup_backward return error')
                break
            time.sleep(1)
        return False        
    def m3_pcb_version(self,data):
        board=data.get('board',False)
        if board==False:
            return {'rep': {'device': 'm3', 'result': 'error'}}
        if board =='lattice':
            command='lV'
        if board == 'beans':
            command='OV'
        command = command.encode('latin-1')
        crc = struct.pack('H', self.crc_func(command))
        command+= crc    
        trace.info('%s' %command)
        self.rcomm.dev_send(self.rcomm.dev_comb.Y, command)
        try:
            r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
            trace.debug('r -> %s' %r)
            return r[1:5].decode('latin-1')
        except:
            trace.error('no ack')
            return False
    def m3_lattice_gen_frame(self,cmd,para):
        command='l'+cmd+para
        command = command.encode('latin-1')
        crc = struct.pack('H', self.crc_func(command))
        command+= crc    
        trace.info('%s' %command)
        self.rcomm.dev_send(self.rcomm.dev_comb.Y, command)
        try:
            r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
            r=r.decode('latin-1')
            if r.startswith('l%sok'%cmd):
                return True
            else:
                return False
        except:
            trace.error('no ack')
            return False
    def process_read_sensor(self,ch):
        cmd='li'
        command = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(command))
        command+= crc    
        trace.info('%s' %command)
        self.rcomm.dev_send(self.rcomm.dev_comb.Y, command)
        try:
            r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
            r=r.decode('latin-1').split(',')
            trace.info('sensors state-->%s' %r[1:7]) 
            ch_list=list(map(int,ch.split(',')))
            sensor={}
            trace.info(ch_list)
            for d in ch_list:
                if (int(r[(d-1)//8+1])>>((d-1)%8))&0x01 == 1:
                    sensor[str(d)]='CLOSE'  
                else:
                    sensor[str(d)]='OPEN' 
            
            return sensor
        except:
            trace.info('no ack')
            return False
    def process_open_door(self):
        cmd='OE'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'OE'):
                    return True
            except:
                trace.error('no ack')
        return False      
    def process_close_door(self):
        cmd='Oe'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'Oe'):
                    return True
            except:
                trace.error('no ack')
        return False   
    def process_led_flash_start(self):  
        freq=100
        cmd='Of%c'%freq
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'Ofok'):
                    return True
            except:
                trace.error('no ack')
        return False     
    def process_read_cup_ss(self):  
        cmd='Op'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'Opok'):
                    return True
            except:
                trace.error('no ack')
        return False 
    def process_led_flash_stop(self):  
        cmd='OF'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                trace.debug('r -> %s' %r)
                if r.startswith(b'OFok'):
                    return True
            except:
                trace.error('no ack')
        return False 
    def process_open_lid(self,data):
        ch=data.get('ch',False)
        if ch ==False:
            return False  
        spd=data.get('spd',False)
        if spd ==False:
            spd=5
        else:
            spd=int(spd)
        time=data.get('time',False)
        if time ==False:
            time=200
        else:
            time=int(time)
        cmd='Ol%c%c%c'%(int(ch),spd,time)
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                #trace.debug('r -> %s' %r)
                if r.startswith(b'Olok'):
                    return True
            except:
                trace.error('no ack')
        return False 
    def process_close_lid(self,data):
        ch=data.get('ch',False)
        if ch ==False:
            return False    
        spd=data.get('spd',False)
        if spd ==False:
            spd=5
        else:
            spd=int(spd)
        time=data.get('time',False)
        if time ==False:
            time=150
        else:
            time=int(time)
        cmd='OL%c%c%c'%(int(ch),spd,time)
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=50
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                #trace.debug('r -> %s' %r)
                if r.startswith(b'OLok'):
                    return True
            except:
                trace.error('no ack')
        return False 
    def process_uv_on(self):
        cmd='OM'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                #trace.debug('r -> %s' %r)
                if r.startswith(b'OEok'):
                    return True
            except:
                trace.error('no ack')
        return False 
    def process_uv_off(self):
        cmd='Om'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                #trace.debug('r -> %s' %r)
                if r.startswith(b'Oeok'):
                    return True
            except:
                trace.error('no ack')
        return False 
    def cup_state_clear(self):
        cmd='Ou'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        retry=3
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                #trace.debug('r -> %s' %r)
                if r.startswith(b'Ouok'):
                    return True
            except:
                trace.error('no ack')
        return False 
    def beans_board_hi(self,retry=100):
        cmd='OH'
        cmd = cmd.encode('latin-1')
        crc = struct.pack('H', self.crc_func(cmd))
        cmd+= crc
        trace.info('%s' %cmd)
        for i in range(0,retry):
            self.rcomm.dev_send(self.rcomm.dev_comb.Y, cmd)
            try:
                r = self.rcomm.dev_comb.Y.q.get(timeout=0.5)
                #trace.debug('r -> %s' %r)
                if r.startswith(b'Ohi'):
                    return True
            except:
                trace.error('no ack')
        return False 
    
def main():
    daemon = Daemon()
    daemon.start()
    while 1:
        time.sleep(1)
    
######################
if __name__ == "__main__":
    
    main()
