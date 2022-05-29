#!/usr/bin/python3

import os
import sys
import time
import fcntl
import serial
import select
import termios
import threading
import socket
from queue import Queue
import select

class Rcomm_Aux_Drop( threading.Thread ):

    def __init__(self,trace):
        super(Rcomm_Aux_Drop, self).__init__()
        self.trace = trace
        self._stop_event = threading.Event()
        self.com_num=0
        self.slave_drop_clear_flag=1
        self.test=1
        self.baudrate=9600
        
        pcname=socket.getfqdn(socket.gethostname())
        if pcname.find('y1'):
            pass
        else:
            self.baudrate=115200
        try:
            self.serial_id='/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DO01N09L-if00-port0'
            self.ser=serial.Serial(self.serial_id,self.baudrate,timeout=1)
            self.ser.q=Queue()
        except:
            trace.info('com unlink')
    
    def join(self, timeout=1):
        self._stop_event.set()
        super(rcomm_aux_drop, self).join(timeout)
    
    def process_rx(self):
        try:
            time.sleep(0.0525)
            data = self.ser.read(self.ser.in_waiting)
            if data ==b'':
                pass
            else:
                self.trace.info('data -> %s' %data)
                self.ser.q.put(data)
        except:
            try:
                serial_list=os.listdir('/dev/serial/by-id/')
                num=len(serial_list)
                if num==self.com_num:
                    pass
                else:
                    self.trace.info('aux com unlink')
                self.com_num=len(serial_list)
            except:
                pass
            #self.trace.error('failed to read aux dev')
            try:
                self.ser=serial.Serial(self.serial_id,self.baudrate,timeout=1)
                self.ser.q=Queue()
                self.trace.info('%s'%self.serial_id)
            except:
                pass
            
    def dev_send(self, dev, data):
        try:
            self.dev_flush(dev)
            dev.write(data)
            return True
        except Exception as ex:
            self.trace.error('failed to write dev: %s' %ex)
            return False
    
    def run(self):
        self.trace.info('hello rcomm_aux_drop') 
        i=0
        com_flag=0
        try:
            serial_list=os.listdir('/dev/serial/by-id/')
            for r in serial_list:
                if r.find('usb-fusionRobotics'):
                    self.serial_id='/dev/serial/by-id/'+r    #drop_aux com exist
                    self.ser=serial.Serial(self.serial_id,self.baudrate,timeout=1)
                    self.ser.q=Queue()
                    trace.info('aux com link')
                    self.slave_drop_clear_flag=1
                    com_flag=0
                else:
                    i=i+1                          
                    if i== len(serial_list):
                        com_flag=1    #drop_aux com not exist
                        self.slave_drop_clear_flag=0             
        except:
            com_flag=1
            self.slave_drop_clear_flag=0  
            
        while not self._stop_event.is_set():
            if com_flag==1:     #drop_aux com not exist
                time.sleep(1)
                try:
                    serial_list=os.listdir('/dev/serial/by-id/')
                    for r in serial_list:
                        if r.find('usb-fusionRobotics'):
                            self.serial_id='/dev/serial/by-id/'+r    #drop_aux com exist
                            self.ser=serial.Serial(self.serial_id,self.baudrate,timeout=1)
                            self.ser.q=Queue()
                            com_flag=0
                            self.slave_drop_clear_flag=1
                        else:
                            i=i+1                          
                            if i== len(serial_list):
                                com_flag=1                     #drop_aux com not exist
                                self.slave_drop_clear_flag=0  
                except:
                    com_flag=1
                    self.slave_drop_clear_flag=0  
            elif com_flag==0:
                self.process_rx()
            else:
                pass
                                        
    def dev_flush(self, dev):
        try:
            self.trace.debug('flush %s' % dev.name)
            dev.flush()
            dev.flushInput()
            dev.flushOutput()
            #dev.queue.clear()
        except:
            self.trace.info('aux com flush failed')
            dev=serial.Serial(self.serial_id,self.baudrate,timeout=1)
        
        
        
