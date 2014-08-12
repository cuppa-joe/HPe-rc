#!/usr/bin/env python
#
# Copyright (c) 2013 Joseph W. Metcalf
#
# Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby 
# granted, provided that the above copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING 
# ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, 
# DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, 
# WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE 
# USE OR PERFORMANCE OF THIS SOFTWARE.
#
# This product contains Uniden proprietary and/or copyrighted information. Used under license.

import sys, io, os
import string
import ConfigParser
import argparse
import urlparse
import time, datetime
import serial
import logging
import array
import struct
import cmd
import json
import wave
import hashlib
import threading
import Queue
import util
import defs

PROMPT = 'Not Connected'
UNIDEN = 'This product contains Uniden proprietary and/or copyrighted information. \nUsed under license.\n'
OK_VAR = ['port1','port2','port1_baud','port2_baud','loglevel','log_file','log_path','rd_input','rd_filter','rd_level','rd_sample','rd_threshold','rd_freq','rd_mode','rd_att','rd_rectime','rd_timeout','rd_file','rd_path','dateformat','mon_cmd','mon_file','mon_expire','mon_format','mon_path','cfg_path','feed_loop','feed_path','feed_delay','web_host','web_port','web_readonly','web_ip','web_browser','web_check','cmd','update_check']
INT_VAR = ['loglevel','port1_baud','port2_baud','rd_sample','rd_threshold','rd_timeout','rd_rectime','rd_level','feed_delay','mon_expire','web_port','web_check','update_check']
OOO_VAR = ['rd_att', 'log_file', 'rd_file', 'mon_file','mon_cmd','feed_loop','rd_scan','rd_filter','web','web_readonly','web_browser']
DIR_VAR = ['rd_path','feed_path','log_path','mon_path','cfg_path']
MOD_VAR = ['rd_mode']
FRQ_VAR = ['rd_freq']
LIST_VAR = ['web_ip']
OPEN_CMD = ['volume','scan','raw','dump','mute','close','cap','att','record','squelch','replay','status','feed','monitor','hold','avoid','next','prev', 'program', 'cmd']

SUB_DICT = {'space': ' ','program': defs.PROGRAM}

REPLAY_STATUS = {'tgid' : 3, 'frequency' : 3, 'mode' : 0, 'att' : 0, 'subtone' : 4, 'nac' : 5, 'service_tag': 6, 'system' : 7,
               'department' : 8, 'channel' : 9, 'squelch' : 0, 'mute' : 0, 'signal' :0, 'favorites_list' :10,
               'uid' : 11, 'system_avoid' : 0, 'department_avoid' : 0, 'channel_avoid' : 0, 'status' : 0, 'service_name' : 0, 
               'subtone_string' : 0, 'replay_status' : 2}

SCAN_STATUS = {'tgid' : 2, 'frequency' : 2, 'mode' : 3, 'att' : 4, 'subtone' : 5, 'nac' : 6, 'service_tag': 7, 'system' : 8,
               'department' : 9, 'channel' : 10, 'squelch' : 11, 'mute' : 12, 'signal' :13, 'favorites_list' :14,
               'uid' : 15, 'system_avoid' : 16, 'department_avoid' : 17, 'channel_avoid' : 18, 'status' : 0, 'service_name' : 0,
               'subtone_string' : 0, 'replay_status' : 0}

WAV_HEADER = {'IART\x40\x00\x00\x00': 8, 'IGNR\x40\x00\x00\x00' : 9, 'INAM\x40\x00\x00\x00' : 10, 'ICMT\x40\x00\x00\x00' : 2, 'ISBJ\x40\x00\x00\x00' : 14, 'ISRC\x10\x00\x00\x00' : 5, 'IKEY\x14\x00\x00\x00' : 7, 'ITCH\x40\x00\x00\x00' : 15}

AUTO_PORT = {'Windows' : ['COM1','COM2','COM3','COM4','COM5','COM6','COM7','COM8','COM9'],
            'Linux' : ['/dev/ttyACM0','/dev/ttyACM1','/dev/ttyUSB0','/dev/ttyUSB1','/dev/ttyUSB2','/dev/ttyS0','/dev/ttyS1','/dev/ttyS2']
            }

DUMP_FMT =  {'hex' : '{0:02X}', 'bin' : '{0:08b}', 'text' : '{c}' }

COMMON_SYSTEM = ['channel','department','system']
ALT_SYSTEM = ['frequency', 'department','system']
INFO_SYSTEM = ['subtone']
COMPARE_SYSTEM = ['status','channel','channel_hold','channel_avoid','department','department_hold','department_avoid','system','system_hold','system_avoid']

HASH_ITEMS=['frequency','channel','channel_hold','channel_avoid','department','department_hold','department_avoid','system','system_hold','system_avoid','signal','uid','status','replay_status']   

queue=Queue.Queue()

def ok():
    print 'Ok.'

def idle(base=0.1):
    time.sleep(base)

def r2r(ser, timeout=0, flush=False):
    global serin
    
    serial_lock = threading.Lock()
    serial_lock.acquire()
    if flush:
        serin=''
        ser.flush()
    start_time=int(time.time())
    rs=None
    while rs==None:
        if ser.inWaiting():
            serin += ser.read(ser.inWaiting())
            if chr(0x0d) in serin:
                linein, sep, serin=serin.partition(chr(0x0d))
                rs = response(linein)
            else:                   # ADDED - REDUCES CPU BY 100X
                idle();             # Thanks, Mark P.  
        if timeout != 0:
            check_time=int(time.time())
            if (check_time - start_time) >= timeout:
                rs='\x00'
    serial_lock.release()
    return rs

def flush(ser):
    rs=r2r(ser, timeout=1, flush=True)

CLEANUP = {'channel': 'TGID : ','tgid' : 'TGID : ', 'frequency' : 'TGID : ', 'uid' : 'UID : ', 'uid' :'UID:'}

def system_cleanup(system):
    for key in CLEANUP:
        if system[key]:
            check=system[key].find(CLEANUP[key])
            if check != -1:
                system[key]=str(system[key][len(CLEANUP[key]):])
    return system

def hash_system(system):
    md = hashlib.md5()
    for item in HASH_ITEMS:
        md.update(system.get(item, item) or item)
    return str(md.hexdigest())

def build_status(list, mapping, **kwargs):
    """Interpret list using dictionary map"""
    global last_system
    system = {}
    if list:    
        for key in mapping:
            if mapping[key]!=0:
                try:
                    system[key] = bool(list[mapping[key]]) and list[mapping[key]].strip() or None
                except:
                    system[key] = None
            else:
                system[key] = None
        for key, value in kwargs.iteritems():
            system[key] = value
        system['time']=str(int(time.time()))
        try:
            system['service_name'] = defs.SERVICE_TYPES[system['service_tag']] or None
        except KeyError:
            system['service_name'] = None
        system['subtone_string'] = subtone(system['subtone'])
        system['sub_uid'] = sub_uid(system['subtone'], system['uid'])
        system.update(prefix_dict(prefix='hp'))
        if (system['squelch']=='1') and (system['mute']=='0'):
            system['status']='Receiving'
        elif system.get('replay_status', None)!=None:
            if system['replay_status']=='STOP':
                system['status']='Replay Stop'
            else:
                system['status']='Replay Mode'
        elif system.get('feed', None)!=None:
            system['status']='Downloading'
        else:
            system['status']='Scanning'
        for item in ['channel','department','system']:
            cmdtype=''.join([item[0].upper(),'HOLD'])
            status=HP_cmd_on_off(ser1, '', type=cmdtype, display=False)
            system[''.join([item,'_','hold'])] = digit_switch(status)
    else:
        for key in mapping:
            system[key] = None
        system['status']='Busy'
    system['hash'] = hash_system(system)
    return system_cleanup(system)
    
def arg_dict(instr):
    try:
        return dict(arg.split('=', 1) for arg in instr.split(' '))
    except:
        logging.error('Invalid Parameter List')
        return []

def path_safe(instr):
    valid_chars = '-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(x if x in valid_chars else '-' for x in instr )
  
def var_sub(instr, subs={}):
    asubs = {}
    asubs.update(subs)
    asubs.update(SUB_DICT)
    try:
        asubs.update({'date':fn_dt(datetime.datetime.now(), config['dateformat'])})
        asubs.update({'config_name': config['config_name']})
    except:
        pass
    for key, value in asubs.items():
        instr = instr.replace('%%(%s)%%' % key, value and path_safe(value) or '')
    return instr

def fn_dt(dt, format='%Y-%m-%d_%H-%M-%S'):
    """Return formated datetime for filenames"""
    return dt.strftime(format)

def fn_cuf(dt, format='%Y-%m-%d_%H-%M-%S'):
    """Convert Uniden-style filename to datetime format"""
    return datetime.datetime.strptime(dt, format)
 
def set_config(key,value,verbose=True):
    step = None
    none = False
    if value==None:
        config[key] = value
    elif key in FRQ_VAR:
        if '.' in value:
            try:
                step=int(float(value)*1000000)
            except:
                logging.error(' '.join(['Invalid Frequency:', key]))
        else:
            try:
                step=int(value)
            except:
                logging.error(' '.join(['Invalid Frequency:',key])) 
        if step:
            if not (25000000 <= step <= 960000000): 
                logging.error(' '.join(['Frequency Out of Range:', key]))
                step=None
    elif key in INT_VAR:
        try:
            step = int(value)
        except:
            logging.error(' '.join(['Integer Required:',key]))
    elif key in OOO_VAR:
        if value.upper() in ['ON','OFF']:
            step = value.upper()
        else:
            logging.error(' '.join(['Select ON or OFF:', key]))
    elif key in MOD_VAR:
        if value.upper() in ['AUTO','AM','FM','NFM']:
            step = value.upper()
        else:
            logging.error(' '.join(['Select AUTO, AM, FM or NFM:', key]))    
    elif key in DIR_VAR:
        try:
            step = os.path.abspath(os.path.expanduser(var_sub(value, {'space' : ' '})))
        except:
            step = None
            logging.error(' '.join(['Invalid Directory:', key]))
    elif key in LIST_VAR:
        if value=='':
            step=None
            none=True
        else:
            try:
                step = value.strip().split(',')
            except:
                step = None
                logging.error(' '.join(['Comma-Separated List Required:',key]))                
    else:
        if value.capitalize()=='None':
            step = None
            none = True
        else:
            step = value
    if step or none:
        config[key]=step
        if verbose:
            print ' '.join(['Ok:',key,'=',str(step)])
    
    if key=='loglevel':
        logging.getLogger().setLevel(int(config['loglevel']))
    
    if key=='web':
        if config['web']=='ON':
            web_server(command='start',port=config['web_port'])
        else:
            web_server(command='stop')
          
    if key=='cmd':
        HP_CMD().onecmd(value)
        
def build_favorites(set=None):
    HP_program_mode(ser1, enter=True, display=False)
    if set:
        for key in favorites:
            if key in set:
                HP_fav_list(ser1,' '.join([key, 'ON']))
            else:
                HP_fav_list(ser1,' '.join([key, 'OFF']))
    HP_fav_list(ser1, '', display=False)
    HP_program_mode(ser1, enter=False, display=False)
    HP_cmd_on_off(ser1,status='OFF', type='CHOLD', display=False)
    
def build_globals():
    r_dict = {}
    r_dict['g_record']=digit_switch(HP_cmd_on_off(ser1, '', type='REC', display=False))
    r_dict['g_mute']=digit_switch(HP_cmd_on_off(ser1, '', type='MUTE', display=False))
    r_dict['g_att']=digit_switch(HP_cmd_on_off(ser1, '', type='GATT', display=False))
    return r_dict
 
def build_volsql():
    r_dict = {}
    r_dict['VOL']=int(HP_cmd_0_15(ser1, val='', type='VOL', display=False))
    r_dict['SQL']=int(HP_cmd_0_15(ser1, val='', type='SQL', display=False))
    return r_dict
 
def prefix_dict(prefix='ajax'):
    global config
    keylist=[]
    for k in config.keys():
        if k.startswith(''.join([prefix,'_'])):
            keylist.append(k)
    return dict((k, config[k]) for k in keylist)

def web_app(environ, start_response):
    import mimetypes
    global last_system
    global config
    global globals
    global volsql
    
    ajax_parameters=prefix_dict()
    JSONMAP = {'ajax/monitor': last_system, '/ajax/system' : last_system, 'ajax/config' : config, 'ajax/favorites' : favorites,
    'ajax/parameters': ajax_parameters, 'ajax/globals' : globals, 'ajax/volsql': volsql, 'ajax/test' : defs.TEST_DATA}
    COMMANDMAP = {'command/quit':'quit','command/feed':'FEED','command/scan':'SCAN', 'command/replay' : 'REPLAY', 'command/cnext' : 'CNEXT', 'command/dnext': 'DNEXT',
    'command/snext':'SNEXT','command/cprev' : 'CPREV', 'command/dprev': 'DPREV','command/sprev':'SPREV', 'command/cap' : 'CAP',
    'toggle/mute':'MUTE', 'toggle/gatt':'GATT','toggle/record':'REC','toggle/chold':'CHOLD', 'toggle/dhold':'DHOLD', 
    'toggle/shold':'SHOLD', 'toggle/cavoid':'CAVOID', 'toggle/davoid':'DAVOID', 'toggle/savoid':'SAVOID',    
    'rep/next' : 'NEXT', 'rep/prev' : 'PREV', 'rep/pause' : 'PAUSE', 'rep/resume' : 'RESUME',
    }
    STARTMAP = {'start/monitor' : 'monitor', 'start/feed' : 'feed', 'kill' : 'kill'}
    UDMAP = {'+/vol':'VOL','-/vol':'VOL','+/sql':'SQL','-/sql':'SQL'}
    FILEMAP = {'feeds.html','monitor.html'}
    PATHMAP = {'feeds' : config['feed_path'], 'monitor' : config['mon_path']}
    POSTMAP = {'post/config' : 'config' , 'post/favorites': 'favorites'}
    REDIRECT = {'jquery.js': 'jquery-1.10.2.min.js', '' : 'hpe-rc.html'}
    FILES = {'hpe-rc.html' : None, 'base.css' : None, 'base.js' : None, 'HPe-rc64.png': None, 'hpe-rc.css' : None,
    'hpe-rc.js' : None, 'jquery-1.10.2.min.js': None, 'jquery-1.8.2.min.js': None, 'favicon.ico' : None ,'config.html': None ,'favorites.html': None,
    'feeds.html' : 'files.html', 'monitor.html': 'files.html'}

    response=None
    request_path=environ.get('PATH_INFO', '').lstrip('/')
    request_hash=environ.get('HTTP_IF_NONE_MATCH', None)
    request_ip=environ.get('REMOTE_ADDR', None)
    request_method=environ.get('REQUEST_METHOD', None)
    headers = []
    if config['web_ip'] and request_ip not in config['web_ip']:
        headers = [('Content-type', 'text/plain')]
        status = '403 Forbidden'
        response=status
        start_response(status, headers)
        return [response]
    status = '200 OK'
    for key, value in JSONMAP.items():
        if (request_path==key) and value:      
            headers = [('Content-type', 'application/json')]
            current_hash=value.get('hash', None)
            if current_hash:
                headers.append(('Etag',str(current_hash)))
            if (request_hash==current_hash) and request_hash!=None:
                    status='304 Not Modified'
                    response=''
            else:
                status = '200 OK'                                
                if key != 'ajax/favorites':
                    value['version'] = version_string()
                headers.append(('Access-Control-Allow-Origin','*'))
                headers.append(('Expires','-1'))
                response=json.dumps(value)
    if response==None:
        try:
            command=request_path.split('/',1)[0]
        except:
            command=None
        for key, value in STARTMAP.items():
            if (request_path==key) and value:
                queue.put({'type': command,'command':value})
                response=''
        for key, value in COMMANDMAP.items():
            if (request_path==key) and value:
                if config['web_readonly']=='OFF':
                    queue.put({'type': command,'command':value})
                response=''
        for key, value in UDMAP.items():
            if (request_path==key) and value:
                if config['web_readonly']=='OFF':
                    queue.put({'type': request_path[0],'command':value})
                response=''
    if response==None and request_method=='POST':
        for key, value in POSTMAP.items():
            if request_path==key:
                request_body_size = int(environ.get('CONTENT_LENGTH', 0))
                request_body = environ['wsgi.input'].read(request_body_size)
                if config['web_readonly']=='OFF':
                    queue.put({'type': command,'command':value, 'data':request_body})
                status = '302 Found'
                headers = [('Content-type', 'text/html'), ('Location', ''.join(['/',value,'.html']))]
                response=''
    if response==None:
        for key, value in PATHMAP.items():
            if request_path==key:
                filenames = os.listdir(value)
                filelist=[filename for filename in filenames]
                response=json.dumps(filelist)
                headers = [('Content-type', 'application/json')]
            split=request_path.rpartition('/')
            if split[0]==key:
                response = open(''.join([value,'/',split[2]]), 'rb').read()             
                status = '200 OK'
                headers = [('Content-type', mimetypes.guess_type(request_path)[0] or 'text/html')]
    if response==None:
        for request, source in FILES.items():
            if request_path==request:
                response = open(''.join(['web',os.sep,source or request_path]), 'rb').read()             
                status = '200 OK'
                headers = [('Content-type', mimetypes.guess_type(source or request_path)[0] or 'text/html')]
            if response=='':
                headers = [('Content-type', 'text/html')]
                status = '204 No Content' 
    if response==None:
        for request, redirect in REDIRECT.items():
            if request_path==request:                                             
                status = '302 Found'
                headers = [('Content-type', 'text/html'), ('Location', ''.join(['/',redirect]))]
                response=''    
    if response==None:            
        status = '404 Not Found'
        headers = [('Content-type', 'text/html')]
        response=status
    headers.append(('Content-Length',str(len(response))))
    start_response(status, headers)
    return [response]
    
def web_server(command='start', port=8000):
    from wsgiref.simple_server import make_server
    global httpd
    
    class LogDevice():
        def write(self, s):
            logging.debug(s)
    
    sys.stderr = LogDevice()
   
    class server_thread(threading.Thread):
        def run(self):
            print
            print 'Starting Web Server...'
            try:
                httpd.serve_forever(poll_interval=0.5)
            except Exception as detail:
                logging.error(' '.join(['Web Server can not be started:',detail]))
                httpd.socket.close()
    
    if httpd and command=='stop':
        print
        print 'Stopping Web Server...'
        print
        threading.Thread(target=httpd.shutdown).start()
        httpd=None
    
    if command=='start':
        if not httpd:
            httpd = make_server(config['web_host'], config['web_port'], web_app)
            server_thread().start()
        else:
            logging.warning('Web Server already started.')

class HP_PROGRAM(cmd.Cmd):
    global config, ser1, ser2
    
    prompt = ''.join(['Program Mode','> '])
    intro = '\n'
    doc_header = 'Available Commands'
    misc_header = 'Additional Topics'
    undoc_header = 'Other Commands'
    ruler = '-'
 
    def emptyline(self):
        pass
        
    def postcmd(self, stop, line):
        print
        return cmd.Cmd.postcmd(self, stop, line)
    
    def precmd(self, line):
        print
        return cmd.Cmd.precmd(self, line)
   
    def help_help(self):
        print 'Type help [topic] for more information on commands and operation.'

    def do_exit(self,line):
        """exit
        Exit programming mode."""
        HP_program_mode(ser1, enter=False)
        HP_cmd_on_off(ser1,status='OFF', type='CHOLD') #HP-1 bug - Channel Hold set after program mode
        return True

    def do_favorites(self, line):
        """favorites [0-256] [ON|OFF]
        Turn favorites lists on or off. Use this command without options
        to display defined favorites lists."""
        HP_fav_list(ser1, line)

class HP_REPLAY(cmd.Cmd):
    global config, ser1, ser2
    
    prompt = ''.join(['Replay Mode','> '])
    intro = '\n'
    doc_header = 'Available Commands'
    misc_header = 'Additional Topics'
    undoc_header = 'Other Commands'
    ruler = '-'
 
    def emptyline(self):
        pass
        
    def postcmd(self, stop, line):
        print
        return cmd.Cmd.postcmd(self, stop, line)
    
    def precmd(self, line):
        print
        return cmd.Cmd.precmd(self, line)
   
    def help_help(self):
        print 'Type help [topic] for more information on commands and operation.'
    
    def do_status(self, line):
        """status
        Display current system information in replay mode."""
        status=HP_rep_status(ser1)
        if not status==None:
            try:
                format_system(build_status(status, REPLAY_STATUS))
            except:
                logging.error('Unable to read status data.')
   
    def do_pause(self,line):
        """pause
        Pause playback."""
        HP_replay_cmd(ser1,type='PAUSE')
 
    def do_next(self,line):
        """next
        Skip to next recording."""
        HP_replay_cmd(ser1,type='NEXT')
 
    def do_prev(self,line):
        """prev
        Return to previous recording."""
        HP_replay_cmd(ser1,type='PREV')
 
    def do_resume(self,line):
        """resume
        Resume playback."""
        HP_replay_cmd(ser1,type='RESUME')
     
    def do_exit(self,line):
        """exit
        Leave replay mode."""
        ok()
        return True
    
class HP_CMD(cmd.Cmd):
           
    global config, ser1, ser2
    
    prompt = ''.join([PROMPT,'> '])
    intro = UNIDEN
    doc_header = 'Available Commands'
    misc_header = 'Additional Topics'
    undoc_header = 'Other Commands'
    ruler = '-'
    
    def emptyline(self):
        pass
        
    def postcmd(self, stop, line):
        print
        return cmd.Cmd.postcmd(self, stop, line)
        
    def precmd(self, line):     
        print
        if self.parseline(line)[0] in OPEN_CMD:
            if not ser1:
                logging.error('HomePatrol must be connected to use this command.')
                return cmd.Cmd.precmd(self, '')
        return cmd.Cmd.precmd(self, line)
    
    def help_help(self):
        print 'Type help [topic] for more information on commands and operation.'

    def do_help(self, line):
        cmd.Cmd.do_help(self, line)
        if line in OPEN_CMD:
            print
            print '        {0}'.format('Note: HomePatrol must be connected to use this command.')
 
    def do_save(self,line):
        """save [name]
        Save current parameter set. Omit the name to save the default set."""
        save_config(set=line)
        
    def do_load(self,line):
        """load [name]
        Load a new parameter set. Omit the name to load the default set."""
        load_config(set=line)
 
    def do_test(self,line):
        """test
        Test command."""
        ok()

    def do_cmd(self, line):
        """cmd
        Send arbitrary command string"""
        HP_any_cmd(ser1, line)
        ok()
 
    def do_checksum(self, status):
        """checksum [ON|OFF]
        Turn HP-1 command checksums ON or OFF."""
        HP_checksum(ser1, status)
 
    def do_debugmode(self,line):
        ser1.write('\t'.join(['cdb','2']))
        ser1.write('\r')
        rs=r2r(ser1)
        print rs
        while True:
            try:
                rs=r2r(ser1)
                print rs[0]
            except KeyboardInterrupt:         
                print
                ser1.flushInput()
                ser1.write('RDB')
                ser1.write('\r')
                ser.flushInput()
                time.sleep(1)
                rs=r2r(ser1, flush=True)
                print rs
                break
 
    def do_web(self,line):
        """web
        Start Web UI. Press Control-C to exit."""
        if not ser1:
            HP_CMD().onecmd('open')        
        if ser1:
            build_favorites()
            set_config('web','ON',verbose=False)
            if config['web_browser']=='ON':
                import webbrowser
                webbrowser.open_new(''.join(['http://', config['web_host']=='' and '127.0.0.1' or config['web_host'], ':', str(config['web_port'])]))
            HP_www()
            
    def do_monitor(self,line):
        """monitor
        Start monitor mode. Press Ctrl-C to exit."""
        HP_monitor(ser1)
        
    def do_version(self,line):
        """version
        Display program information"""
        print version_string() 
       
    def do_set(self, line):
        """set parameter=[value] ...
        Set one or more parameters. 
        Use set with no options for a list of available parameters.
        """
        if line:
            args=arg_dict(line)
            for key in args:
                if key in OK_VAR:
                    set_config(key, args[key])
                else:
                    logging.error('Unknown Parameter')
        else:
            HP_CMD().onecmd('get')
            
    def do_get(self,line):
        """get [match]
        List all matching parameters.
        Use get without an option for a full list of parameters. """    
        if line:
            print ''.join(['Parameters Matching [',line,']'])
        else:
            print 'Available Parameters:'
        print
        for key in OK_VAR:
            if key in OOO_VAR:
                args = '[ON|OFF]'
            elif key in MOD_VAR:
                args = '[AUTO|AM|FM|NFM]'
            elif key in INT_VAR:
                args = '[Integer]'
            elif key in FRQ_VAR:
                args = '[MHZ|HZ]'
            elif key in LIST_VAR:
                args = '[X,Y,Z]'
            else:
                args = '[String]'
            if line:
                if key.find(line) != -1:
                    print '{0: <62} {1: <15}'.format('='.join([key, str(config[key])])[:61], args)
            else:
                try:
                    print '{0: <62} {1: <15}'.format('='.join([key, str(config[key])])[:61], args)
                except:
                    pass
        
    def do_scan(self, line):
        """scan
        Set HomePatrol to Scan Mode."""
        HP_scanmode(ser1)

    def do_program(self, line):
        """program
        Set scanner to Program Mode. Only programming commands will be available."""            
        HP_program_mode(ser1, enter=True)
        HP_PROGRAM().cmdloop()

    def do_replay(self, line):
        """replay
        Set scanner to Replay Mode. Only replay commands will be available."""            
        HP_replaymode(ser1)
        HP_REPLAY().cmdloop()
        
    def do_cap(self, line):
        """cap
        Capture a screenshot.  
        Images can not be captured when receiving in Scan Mode unless 
        recording is disabled by removing the batteries and using AC power."""
        HP_screencap(ser1)

    def do_status(self, line):
        """status
        Display current system information in scan mode."""
        status=HP_status(ser1)
        if not status==None:
            try:
                format_system(build_status(status, SCAN_STATUS))
            except:
                logging.error('Unable to read status data.')
                
    def do_raw(self, line):
        """raw
        Read raw discriminator data from scanner using set parameters."""    
        HP_rawmode(ser1,freq=config['rd_freq'],mode=config['rd_mode'],att=config['rd_att'],filter=config['rd_filter'])
        HP_rawread(ser1,ser2,file=config['rd_file'],timeout=config['rd_timeout'], record_time=config['rd_rectime'])

    def do_dump(self, line):
        """dump [hex|bin|text]
        Raw Mode with data slicer hex, binary or text dump."""    
        HP_rawmode(ser1,freq=config['rd_freq'],mode=config['rd_mode'],att=config['rd_att'])
        HP_rawread(ser1,ser2,file=config['rd_file'],timeout=config['rd_timeout'], record_time=config['rd_rectime'], dump=True, strfmt=str(line), wav=False)
       
    def do_open(self, line):
        """open
        Connect HomePatrol to serial port.""" 
        HP_open(config['port1'], config['port2'])
        if config['hp_model'] and ser1:
            self.prompt = ''.join([config['hp_model'],'> '])
  
    def do_close(self, line):
        """close
        Close all open serial ports.""" 
        global ser1, ser2
        if ser1:
            logging.debug(' '.join(['Close',':',config['port1'],]))
            ser1.close()
            ser1=None
            ok()
        if ser2:
            logging.debug(' '.join(['Close',':',config['port2'],]))
            ser2.close()
            ser2=None
        self.prompt = ''.join([PROMPT,'> '])

    def do_feed(self,status):
        """feed [ON|OFF]
        Turn audio feed download ON or OFF.
        Use this command without an option to check current setting."""
        cmd=HP_cmd_on_off(ser1, status, type='STS', cmd='AUF')
        if cmd=='ON':
            HP_audio_feed(ser1)

    def do_volume(self,vol):
        """volume [0-15]
        Set volume level on scanner."""
        HP_cmd_0_15(ser1,val=vol, type='VOL')
 
    def do_squelch(self,sql):
        """squelch [0-15]
        Set squelch level on scanner."""
        HP_cmd_0_15(ser1,val=sql, type='SQL')    
 
    def do_mute(self,status):
        """mute [ON|OFF]
        Turn mute ON or OFF.
        Use this command without an option to check current setting."""
        HP_cmd_on_off(ser1, status, type='MUTE')
 
    def do_att(self,status):
        """att [ON|OFF]
        Turn global attenuation ON or OFF.
        Use this command without an option to check current setting."""
        HP_cmd_on_off(ser1, status, type='GATT')

    def do_record(self,status):
        """record [ON|OFF]
        Turn audio recording ON or OFF.
        Type record without an option to check current setting."""
        HP_cmd_on_off(ser1, status, type='REC')

    def do_bye(self, line):
        """bye
        Exit program.""" 
        HP_CMD().onecmd('close')
        web_server(command='stop')
        return True
        
    def do_hold(self,line):
        """hold [system|department|channel] [ON|OFF]
        Set category hold status. Use this command without a switch option
        to check current setting."""
        HP_hold_avoid(ser1, cmd=line, type='HOLD')

    def do_avoid(self,line):
        """avoid [system|department|channel] [ON|OFF]
        Set category avoid status. Use this command without a switch option
        to check current setting."""
        HP_hold_avoid(ser1, cmd=line, type='AVOID')
        
    def do_next(self,line):
        """next [system|department|channel]
        Set next system, department or channel. This command defaults to
        channel control if an option is not specified."""
        HP_hold_avoid(ser1, cmd=line, type='NEXT')
    
    def do_prev(self,line):
        """next [system|department|channel]
        Set previous system, department or channel. This command defaults to
        channel control if an option is not specified."""
        HP_hold_avoid(ser1, cmd=line, type='PREV')

def checksum(st):
    return str(reduce(lambda x,y:x+y, map(ord, st)))

def command(cmd, *args, **kwargs):
    """Build command string for HP"""
    flag=kwargs.get('flag', None)
    if cmd:
        base = ''.join([cmd,'\t','\t'.join([str(x) for x in args]),'\t'])
    else:
        base = ''.join(['\t'.join([str(x) for x in args[0]]),'\t'])
    return ''.join([base, flag and flag or checksum(base),'\r'])

def checkerr(*args, **kwargs):
    error=False
    display=kwargs.get('display', True)
    status=0
    if 'ERR' in args[0]:
        status=1
        error=True
    if 'NG' in args[0]:
        status=2
        error=True
    if error and display:
        logging.error(status==2 and 'Command Not Available' or status==1 and 'Invalid Command' or status==3 and 'No Data Available')
    elif display:
        logging.debug('OK')
        return False
    return error

def response(st):
    return st.split('\t')

def subtone(code):
    try:
       icode=int(code)
    except:
        return None    
    if 64 <= icode <= 113:
        return defs.CTCSS[code]
    if 128 <= icode <= 231:
        return defs.DCS[code]    
    if icode==0 or icode==127:
        return ''
        
def sub_uid(code, uid):
    try:
       icode=int(code)
    except:
        icode=None    
    if icode:
        if 64 <= icode <= 113:
            return 'CTCSS'
        if 128 <= icode <= 231:
            return 'DCS'   
    elif uid and uid!='':
        return 'UID'
    return ''
        
def csv_system(system, short=True):
    output = ''.join([var_sub(config['mon_format'], system),'\n'])
    return output
    
def compare_systems(system1, system2): 
    if system1 and system2:
        for key in COMPARE_SYSTEM: # Only compare items we're interested in - some fields are not always available 
            if system1[key] != system2[key]:
                return False
    else:
        return False
    return True

def digit_switch(s):
    return s=='ON' and '1' or '0'

def format_system(system, monitor=False, header=True, systems=True, delay=2, other_system=None):
    global last_system, display_system, timer
    current_timer = int(time.time())
    if not system and last_system:
        system=last_system     
        if last_system['channel']:
            if other_system:
                display_system=other_system
                last_system=None
    if not monitor:
        display_system=COMMON_SYSTEM
    elif (delay <= current_timer - timer <= delay*2):
        display_system=COMMON_SYSTEM if (display_system==ALT_SYSTEM or display_system==None) else ALT_SYSTEM
        timer=int(time.time())
    elif last_system and compare_systems(system,last_system) and monitor:
        last_system=system        
        return
    else:
        timer=int(time.time())
        last_system=system
        if not display_system:
            display_system=COMMON_SYSTEM
    if header:
        for (item,alt) in zip(COMMON_SYSTEM, ALT_SYSTEM):
            if item==alt or not monitor:
                print '{0: <25}'.format(item.upper()),
            else:
                print '{0: <25}'.format('/'.join([item.upper(),alt.upper()])),
        print
    if systems:
        for key in display_system:
            if system[key]:
                offset = 0
                print '{0}{1: <25}'.format('', format_data(system, key)[offset:24+offset]),
            else:
                print '{0}{1: <25}'.format('', '---'),
    if monitor:
        print '\r',
    else:
        print
        if system['service_tag'] and system['frequency']:
            print
            print format_data(system, 'frequency'),
        if system['nac'] and system['nac'] !='NONE':
            print
            print format_data(system, 'nac'),
        elif system['subtone']:
            print
            print format_data(system, 'subtone'),  
        if system['uid']:
            print
            print format_data(system, 'uid'),
        print
 
def format_data(system,type):
        if type=='frequency':
            return ''.join([str('{0: <15}'.format(defs.SERVICE_TYPES[system['service_tag']])),str('{0: >9}'.format(system['frequency']))])
        if type=='subtone':
            if system['nac']!='NONE':
                return ''.join([str('{0: <15}'.format(' '.join(['NAC',system['nac']]))), str('{0: >9}'.format(system['mode']))])
            else:
                sth=sub_uid(system['subtone'], system['uid'])
                if sth=='UID':
                    sto=system['uid']
                else:
                    sto=subtone(system['subtone'])
                return ''.join([str('{0: <15}'.format(' '.join([sth, sto]))), str('{0: >9}'.format(system['mode']))])
        if type=='service_tag':
            return str('{0: <15}'.format(defs.SERVICE_TYPES[system['service_tag']]))
        if type=='uid':
            return ''.join([str('{0: <15}'.format('UID:')), str('{0: >9}'.format(system['uid']))])
        if type=='nac':
            return str('{0: <15}'.format(' '.join(['NAC',system['nac']])))
        if type=='mode':
            return str('{0: >8}'.format(system['mode']))
        if type=='signal':
            level=int(system['signal'])
            return ''.join([str('{0: <19}'.format('Signal:')),str('{0: <5}'.format('*' * level ))])            
        return str(system[type])

def check_database(database):
    age = datetime.datetime.now() - fn_cuf(database, format='%m/%d/%Y') 
    if age.days>14:
        logging.warning('HP Database is {0} days old.'.format(age.days))
    return

def HP_hold_avoid(ser, cmd, type='HOLD'):
    command=cmd.upper().split(' ')
    if command[0] == '':
        command[0] = 'CHANNEL'
    if len(command)==1:
        command.append('')
    if command[0] in ['CHANNEL','DEPARTMENT','SYSTEM'] and command[1] in ['','ON','OFF']:
        status=''.join([command[0][:1],type]) 
        HP_cmd_on_off(ser,status=command[1], type=status)
    else:
        logging.error('Invalid Parameter')
    
def HP_open(port1, port2):
    global ser1, ser2, sio1
    if port1 and port1.upper()=='AUTO':
        import platform
        try:
            for p in AUTO_PORT[platform.system()]:
                try:
                    ser1 = serial.Serial(p, config['port1_baud'], timeout=0.5, writeTimeout=2)
                    print ' '.join(['Trying',p,'...'])
                    model=HP_model(ser1)
                    if model:
                        config['port1']=p
                        break
                    else:
                        ser1.close()
                except:
                    pass
            print
        except:
            logging.error('Unable to detect serial port.')
            port1=None
    else:
        if not ser1:
            try:
                ser1 = serial.Serial(port1, config['port1_baud'], timeout=0.4)             
            except:
                logging.error(' '.join(['Unable to open port:',str(port1),'(Input)']))
                port1=None
        else:
            logging.info('Port is OPEN')
    if port1:
        try:
            ser1.flush()
            logging.debug(' '.join(['Open',':',config['port1']]))
            model=HP_model(ser1)
            logging.debug(' '.join(['Model:',model]))
            firmware,database,help=HP_version(ser1)
            logging.debug(' '.join(['Version:',firmware,'HPDB:',database,'HELP:',help]))
            config['hp_model']=model
            config['hp_firmware']=firmware
            config['hp_database']=database
        except Exception as detail:
            logging.error('HomePatrol not found.')
            ser1=None
    if ser1:
        print ' '.join([model,firmware,'connected.',''.join(['(',config['port1'],')'])])
        check_database(config['hp_database'])
    if port2:
        try:
            ser2 = serial.Serial(port2, config['port2_baud'], timeout=0.4)             
        except:
            logging.error(' '.join(['Unable to open port:',str(port2),'(Output)']))
            port2 = None
    if ser2:
        print ' '.join(['Data port connected.',''.join(['(',config['port2'],')'])])


def HP_screencap(ser):
    logging.debug('CMD : Capture Screenshot')
    ser.write(command('cdb','C', flag='1')) # cdb<tab>C<tab>1<enter>
    rs=r2r(ser)
    if not checkerr(rs):
        ser.write('cap\r')
        ok()

def HP_checksum(ser, status):
    logging.debug('CMD : Checksum')
    if status.upper() in ['','ON','OFF']:
        flag=digit_switch(status.upper())
        ser.write(command('cdb','M', flag=flag))    
        print command('cdb','M', flag=flag)
        rs=r2r(ser)
        if not checkerr(rs):
            ok()
    else:
        logging.error('Select ON or OFF') 

def HP_fav_list(ser, cmd='', display=True):
    global favorites
    args=cmd.upper().split(' ')    
    index=None
    if len(args)==2:
        try:
            index=int(args[0])
        except:
            index=None   
    if index != None:
        status=args[1].upper()
        if 0 <= index <= 256 and status in ['ON','OFF']:
            ser.write(command('RMT', 'HFAV', str(index), status))
            rs=r2r(ser)
        else:
            logging.error('Invalid Parameter')
    else:   
        favorites={}
        for x in range(0,256):
            ser.write(command('RMT', 'HFAV', str(x)))
            rs=r2r(ser)
            if not checkerr(rs) and (rs[3]!='' and rs[4]!=''):
                favorites[str(x).zfill(3)]={'name':rs[4], 'status':rs[3]}
                if display:
                    print '{0: <3} {1: >3} {2: <25}'.format(x,rs[3],rs[4])
            else:
                break

def HP_program_mode(ser, enter=True, display=True):
    if enter:
        logging.debug('CMD : Enter Program Mode')
        ser.write(command('RMT','PRG'))
    else:
        logging.debug('CMD : Exit Program Mode')
        ser.write(command('RMT','EPG'))
    rs=r2r(ser)
    if not checkerr(rs) and display:
        ok()
    ser.flush()

def HP_any_cmd(ser, line='RMT MODEL', display=True):
    logging.debug(''.join(['CMD : ',line]))
    ser.write(command(None, line.upper().split()))
    rs = r2r(ser)
    if not checkerr(rs, display=display):
        if display:
            print rs
            print

def HP_replay_cmd(ser, type='NEXT', display=True):
    logging.debug(''.join(['CMD : Replay ',type]))
    ser.write(command('RMT','REP',type))
    rs = r2r(ser)
    if not checkerr(rs, display=display):
        if display:
            ok()

def HP_cmd_0_15(ser, val=8, type='VOL', display=True):
    try:
        value=int(val)
    except:
        value=-1
    if 0 <= value <= 15:    
        logging.debug(''.join(['CMD : Set ',type,' ','(',str(val),')']))
        ser.write(command('RMT',type,str(val)))
        rs = r2r(ser)
        if not checkerr(rs, display=display) and display:
            ok()
    elif value==-1:
        logging.debug(''.join(['CMD : Get ',type,]))
        ser.write(command('RMT',type))
        #rs = response(ser.readline())
        rs = r2r(ser)
        if not checkerr(rs, display=display):
            if display:
                print ''.join([type,' is ',rs[2],'.'])
            else:
                return rs[2]
    else:
        logging.error('Integer required: 0-15')

def HP_cmd_on_off(ser,status=None,type='MUTE', cmd='RMT', display=True):
    if status.upper() in ['','ON','OFF']:
        if status=='':
            status=None
        logging.debug(''.join(['CMD : Set/Get',' ',type,' ','(',str(status),')'])) 
        if status:
            ser.write(command(cmd,type,status.upper()))
        else:
            ser.write(command(cmd,type)) 
        rs = r2r(ser)
        if not checkerr(rs, display=display):
            if status==None:
                if display:
                    print ''.join([type,' is ',rs[2],'.'])
                else:
                    return rs[2]
            else:
                if type !='STS' and display:
                    ok()
                return status.upper()
    else:
        logging.error('Select ON or OFF')

def toggle(input=None):
    if input:
        return 'ON' if (input=='OFF') else 'OFF'
    return input

def wav_meta(header):
    status = [None] * 20
    for key in WAV_HEADER:
        idx=header.find(key)
        if idx != -1:
            dll=ord(key[4:5])
            if WAV_HEADER[key] == 7:
                status[WAV_HEADER[key]]=str(struct.unpack('>I',header[idx+8+12:idx+8+12+4])[0])
            elif WAV_HEADER[key] == 5:
                substring = header[idx+8:idx+dll+8].split('\x00', 1)[0]
                if substring == 'None':
                    status[WAV_HEADER[key]]=0
                else:
                    code = substring.partition(':')
                    tone = code[2].rstrip('Hz').lstrip()
                    if code[0]=='CTCSS':
                        for search in defs.CTCSS:
                            if defs.CTCSS[search] == tone:
                                status[WAV_HEADER[key]]=search
                    if code[0]=='DCS':
                        for search in defs.DCS:
                            if defs.DCS[search] == tone:
                                status[WAV_HEADER[key]]=search
            else:
                status[WAV_HEADER[key]]=header[idx+8:idx+dll+8].split('\x00', 1)[0]
    return status

def HP_audio_feed(ser, display=True, web_mode=False):
    loop = True
    while loop:
        if not web_mode:
            loop = config['feed_loop']=='ON' and True or False
        else:
            loop = False
        filename='0'
        try:
            while bool(filename):
                logging.debug('CMD : Get Audio Info')
                ser.write(command('AUF','INFO'))
                rs=r2r(ser)
                if not checkerr(rs) and len(rs)>=4:
                    filename=rs[2]
                    filesize=rs[3]
                    filedate=rs[4]
                    ser.write(command('AUF','INFO','ACK'))
                else:
                    filename=''
                if bool(filename):
                    filedatetime = fn_cuf(filename[:-4])
                    newfilename = '.'.join([fn_dt(filedatetime, format=config['dateformat']),'wav'])
                    jsonfile = '.'.join([fn_dt(filedatetime, format=config['dateformat']),'json'])
                    if display:
                        print '{0: <25} {1: <25} {2: <25}'.format('Download Audio File',newfilename,' '.join([filesize,'bytes']))
                        print
                    block='0'
                    data=None
                    buffer=''
                    while block != 'EOT':
                        if not data:
                            ser.write(command('AUF','DATA'))
                        else:
                            ser.write(command('AUF','DATA','ACK'))
                        rs=r2r(ser)
                        if not checkerr(rs):
                            block=rs[2]
                            data=rs[3]
                            if block !='EOT':
                                try:
                                    blk=int(block)
                                except:
                                    print
                                    logging.error('Invalid Data Received.')
                                    ser.write(command('AUF','DATA','CAN'))
                                    return
                                if blk==1 and buffer=='':
                                    status= wav_meta(data.decode('hex').split('fmt ', 1)[0])
                                    
                                    d_system = build_status(status, SCAN_STATUS, hp_mode='feed')
                                    format_system(d_system, monitor=True, header=not web_mode)                                    
                                    if display:
                                        print
                                    path='.'
                                    if config['feed_path']:
                                        path=var_sub(config['feed_path'], build_status(status, SCAN_STATUS))
                                    try:
                                        wav = open(check_path(path, newfilename), 'wb')
                                        jsf = open(check_path(path, jsonfile), 'wb')
                                    except IOError as detail:
                                        logging.error(detail)
                                        break  
                                    d_system['filename'] = newfilename
                                    json.dump(d_system, jsf)
                                elif blk & 1:                                        
                                    if len(data)==4096:
                                        complete=float(len(buffer)) / float(filesize) * 100
                                        if display:
                                            print '\r{0:4.1f}%'.format(complete),
                                        sys.stdout.flush()
                                buffer += data.decode('hex')
                        else:
                            break
                    ser.write(command('AUF','DATA','ACK'))
                    print '{0: <25}\r'.format('\r'),
                    wav.write(buffer)
                    wav.close()
                    jsf.close()
                else:
                    if loop:
                        print 'Waiting...\r',
                        sys.stdout.flush()                      
                        time.sleep(config['feed_delay']/1000)
                    elif display:
                        print
                        print 'No more files to download.'
        except KeyboardInterrupt:
            print
            loop = False
            ser.flushInput()
            logging.warning('Feed Mode aborted.')
            ser.write(command('AUF','DATA','CAN'))
            ser1.flushInput()
            rs = response(ser.readline())
            checkerr(rs)
            try:
                wav.close()
            except:
                pass
    ser.write(command('AUF','STS','OFF'))
    rs = response(ser.readline())
    checkerr(rs)
      
def HP_scanmode(ser, display=True):
    logging.debug(''.join(['CMD : Set Scan Mode']))
    ser.write(command('RMT','JPM','SCN_MODE'))
    if not checkerr(response(ser.readline()), display=display):
        if display:
            ok()

def HP_replaymode(ser, display=True):
    logging.debug(''.join(['CMD : Set Replay Mode']))
    ser.write(command('RMT','JPM','REP_MODE'))
    if not checkerr(response(ser.readline()), display=display): 
        if display:
            ok()

def HP_model(ser):
    logging.debug('CMD : Get Model')
    ser.write(command('RMT','MODEL'))
    rs = r2r(ser, timeout=2)
    if not checkerr(rs):
        return rs[2]
    return 'None'

def HP_version(ser):
    logging.debug('CMD : Get Version')
    ser.write(command('RMT','VERSION'))
    rs = r2r(ser)
    if not checkerr(rs):
        return rs[2],rs[3],rs[4]
    return '','',''

def HP_status(ser, display=True):
    logging.debug('CMD : Get Status')
    ser.write(command('RMT','STATUS'))
    rs = r2r(ser)
    if not checkerr(rs, display=display):
        return rs
    return None

def command_check():
    command=util.getkey()
    if command=='i':
        format_system(None, monitor=True, header=False, other_system=INFO_SYSTEM)
    if command=='j':
        HP_scanmode(ser1, display=False)
    if command=='r':
        HP_replaymode(ser1, display=False) 
    if command=='x':
        cmd=HP_cmd_on_off(ser1, 'ON', type='STS', cmd='AUF')
        if cmd=='ON':
            HP_audio_feed(ser1, display=False, web_mode=True)
    if command=='m':
        status=HP_cmd_on_off(ser1, '', type='MUTE', display=False)
        HP_cmd_on_off(ser1, toggle(status), type='MUTE', display=False)
    if command=='n':
        HP_cmd_on_off(ser1, status='', type='CNEXT', display=False)
    if command=='p':
        HP_cmd_on_off(ser1, status='', type='CPREV', display=False)
    if command=='a':
        HP_cmd_on_off(ser1, 'ON', type='CAVOID', display=False)
    if command=='+':
        status=int(HP_cmd_0_15(ser1, val='', type='VOL', display=False))
        if status!=15:
            HP_cmd_0_15(ser1, val=status+1, type='VOL', display=False)
    if command=='-':
        status=int(HP_cmd_0_15(ser1, val='', type='VOL', display=False))
        if status!=0:
            HP_cmd_0_15(ser1, val=status-1, type='VOL', display=False)
    if command=='c' or command=='s' or command=='d':
        cmdtype=''.join([command.upper(),'HOLD'])
        status=HP_cmd_on_off(ser1, '', type=cmdtype, display=False)
        HP_cmd_on_off(ser1, toggle(status), type=cmdtype, display=False)
    if command=='q':
        return False
    else:
        return True

def web_config(data):
    new_config=dict(urlparse.parse_qsl(data))
    for key, value in new_config.items():
        if key in OK_VAR:
            set_config(key, value, verbose=False)
    if 'form_cmd' in new_config:
        if new_config['form_cmd']=='restart':
            web_server(command='stop')
            web_server(command='start',port=config['web_port'])
            
def web_favorites(data):
    build_favorites(dict(urlparse.parse_qsl(data)))

def server_queue():
    global volsql
    task=None
    quit=True
    try:
        task=queue.get_nowait()
    except Queue.Empty:
        idle()
    if task:
        if task['type']=='post' and task['command']=='config':
            web_config(task['data'])
        if task['type']=='post' and task['command']=='favorites':
            web_favorites(task['data'])
        if task['type']=='toggle':
            status=HP_cmd_on_off(ser1, '', type=task['command'], display=False)
            HP_cmd_on_off(ser1, toggle(status), type=task['command'], display=False)
        if task['type']=='command':
            if task['command']=='SCAN':
                HP_scanmode(ser1, display=False)
            elif task['command']=='REPLAY':
                HP_replaymode(ser1, display=False)
            elif task['command']=='CAP':
                HP_screencap(ser1)
            elif task['command']=='FEED':
                cmd=HP_cmd_on_off(ser1, 'ON', type='STS', cmd='AUF')
                if cmd=='ON':
                    HP_audio_feed(ser1, display=False, web_mode=True)
            elif task['command']=='quit':
                quit=False
            else:
                HP_cmd_on_off(ser1, status='', type=task['command'], display=False)
        if task['type']=='+':
            status=int(HP_cmd_0_15(ser1, val='', type=task['command'], display=False))
            if status!=15:
                HP_cmd_0_15(ser1, val=status+1, type=task['command'], display=False)
                volsql[task['command']]=status+1
        if task['type']=='-':
            status=int(HP_cmd_0_15(ser1, val='', type=task['command'], display=False))
            if status!=0:
                HP_cmd_0_15(ser1, val=status-1, type=task['command'], display=False)
                volsql[task['command']]=status-1
        if task['type']=='rep':
            HP_replay_cmd(ser1, type=task['command'], display=False)
        queue.task_done()
    return quit

def HP_www():
    print 'Press Control-C to exit.'
    while True:
        try:
            task=None
            try:
                task=queue.get_nowait()
            except Queue.Empty:
                idle()
            if task:
                print
                if task['type']=='post' and task['command']=='config':
                    web_config(task['data'])
                if task['type']=='post' and task['command']=='favorites':
                    web_favorites(task['data'])
                if task['type']=='kill':
                    if config['web_readonly']=='OFF':
                        HP_CMD().onecmd('bye')
                        raise Exception('Program terminated.')
                if task['type']=='start':
                    if task['command']=='monitor':
                        HP_monitor(ser1)
                    if task['command']=='feed':
                        cmd=HP_cmd_on_off(ser1, 'ON', type='STS', cmd='AUF')
                        if cmd=='ON':
                            HP_audio_feed(ser1, display=False, web_mode=False)
                if task['type']=='command':
                    if task['command']=='exit':
                        print
                        break
                queue.task_done()
        except KeyboardInterrupt:         
            print
            break

def status_mode(status):
    if status.get('channel', None)==None and status.get('system', None)==None and status.get('system', None)==None:
        return False
    return True
    
def HP_monitor(ser):
    global globals
    global volsql
    try:
        oldterm, oldflags = util.set_term()
    except AttributeError:
        pass
    last_status = {}
    hash=None
    idle = True
    alternate=True
    web_check=0
    if config['mon_file']=='ON':
        filename = check_path(config['mon_path'], '.'.join([fn_dt(datetime.datetime.now(), format=config['dateformat']),'txt']))
    format_system(None, monitor=True, header=True, systems=False)
    while True:
        if not server_queue():
            print
            break
        try:
            if alternate:
                volsql = build_volsql()
            alternate=not alternate
            if idle and config['web_check']>0:
                if (int(time.time())-web_check)>config['web_check']:
                    cmd=HP_cmd_on_off(ser1, 'ON', type='STS', cmd='AUF')
                    if cmd=='ON':
                        HP_audio_feed(ser1, display=False, web_mode=True)
                    web_check=int(time.time())
            status = build_status(HP_status(ser, display=False), SCAN_STATUS, hp_mode='monitor')   
            if not status_mode(status):
                status = build_status(HP_rep_status(ser, display=False), REPLAY_STATUS, hp_mode='replay')
            globals = build_globals()
            if status: 
                format_system(status, monitor=True, header=False)
                if config['mon_cmd']=='ON':
                    if not command_check():
                        print
                        break
                sys.stdout.flush()
                if status['channel']: 
                    if last_status and idle:
                        elasped = int(time.time())-int(last_status['time'])
                    else:
                        elasped = config['mon_expire']
                    if not compare_systems(status, last_status) or (config['mon_expire']!=0 and elasped>config['mon_expire']):
                        if config['mon_file']=='ON':
                            try:
                                f = open(filename, 'a+b')
                            except IOError:
                                time.sleep(1) # back off and try once more
                                f = open(filename, 'a+b')
                            f.seek(0,2) # Make sure we're at EOF.
                            f.write(csv_system(status, short=False))
                            f.close()
                        last_status=status
                        idle=False
                else:
                    idle=True
            else:
                time.sleep(1) # Status not available. This may be a temporary, i.e. menu access on scanner, so wait a bit.
        except KeyboardInterrupt:         
            print
            break
        except Exception as detail:
            pass
    if config['mon_file']=='ON':
        pass
    try:
        util.restore_term(oldterm, oldflags)
    except AttributeError:
        pass
    flush(ser)
    global last_system, display_system, timer
    last_system, display_system, globals=None, None, None
    timer=0
    
def HP_rep_status(ser, display=True):
    logging.debug('CMD : Get Replay Status')
    ser.write(command('RMT','REP_STATUS'))
    rs = r2r(ser)
    if not checkerr(rs, display=display):
        return rs
    return None
    
def HP_rawmode(ser,freq=162500000,mode='AUTO',att='OFF',filter='OFF'):
    logging.debug('CMD : Set Raw Mode')
    ser.write(command('RMT','SFREQ'))
    rs = response(ser.readline())
    if checkerr(rs, display=False):
        pass #Raw mode may already be set - try parameters before bailing out
    logging.debug('CMD : Set Raw Mode Parameters')    
    try:
        if float(config['firmware']) >= 2.03:
            ser.write(command('RMT','SFREQ',str(freq),mode,att,filter))
        else:
            ser.write(command('RMT','SFREQ',str(freq),mode,att))
    except:
        ser.write(command('RMT','SFREQ',str(freq),mode,att))
    rs = response(ser.readline())
    if checkerr(rs):
        return False
    
def data_slice(sample, level=2):
    base_sample=config['rd_threshold']
    if level==4:
        xa=base_sample-(base_sample / 2)
        xb=base_sample+(base_sample / 2)
        if 0 < sample < xa:
            return 0
        if xa < sample < base_sample:
            return 1           
        if base_sample < sample <= xb:
            return 2
        return 3
    else:
        if sample >= base_sample:
            return 1
        return 0
    return 0

def HP_rawread(ser1,ser2=None,file=None, record_time=0, timeout=3, dump=False, strfmt=None, wav=True, filter=False):
    start_time=int(time.time())
    lread_time=int(time.time())
    temp = []
    samples = []
    hexdump = []
    wavsamp=''
    ws=[]
    wavinput = config['rd_input'] and True or False
    if wavinput:
        filename = check_path(config['rd_path'], config['rd_input'])
        i_f = wave.open(filename,'rb')
        nchannels, sampwidth, framerate, nframes, comptype, compname = i_f.getparams()
        if (nchannels!=1) and (sampwidth!=2) and (framerate!=38400):
            i_f.close()
            print
            logging.warning('Invalid WAV input file.')
            wavinput=false
            set_config('rd_input', None)
    else:
        logging.debug('CMD : Start Raw Mode')
        ser1.write(command('RMT','SFREQ','START'))
    if file=='ON':
        filename = check_path(config['rd_path'], '.'.join([fn_dt(datetime.datetime.now(), format=config['dateformat']),wav and 'wav' or 'dat']))
        if wav:
            o_f = wave.open(filename,'wb')
            nchannels = 1
            sampwidth = 2
            framerate = 38400
            nframes = 0
            comptype = "NONE"
            compname = "not compressed"
            o_f.setparams((nchannels, sampwidth, framerate, nframes, comptype, compname))
        else:
            o_f = open(filename, 'wb')   
    bytecounter = 0
    his=config['rd_threshold']
    los=config['rd_threshold']
    samplesize=config['rd_sample']
    level=config['rd_level']
    baud=samplesize * 75
    spb = samplesize * (16 / level)
    if not dump:
        print '{0: >18}'.format('Raw Mode Running'),
        if wavinput:
            print '{0: >18}'.format('WAV Input'),
        else:
            print '{0: >18}'.format(' '.join([str(config['rd_freq']),'hz'])),  
        print '{0:>18}'.format('LO - TH - HI'),
        print '{0:>18}'.format(' '.join([str(samplesize),'samples/sec']))
    while True:
        try:
            if not wavinput:
                waiting = ser1.inWaiting()
                input=ser1.read(waiting)
            else:
                input=i_f.readframes(1)
            if len(input)>0:
                lread_time=int(time.time())
                elapsed = datetime.timedelta(seconds=(lread_time - start_time))
            temp += list(array.array('B',input))
            while len(temp)>=2:
                h_byte=temp.pop(0)
                if not wavinput:
                    while (h_byte & 128) == 0:
                        h_byte=temp.pop(0)                
                if len(temp) != 0:
                    l_byte=temp.pop(0)
                    if (l_byte & 128) == 0 or wavinput:
                        if not wavinput:
                            atn = int((((h_byte ^ 128) & 31) << 5) | (l_byte & 31))
                        else:
                            atn = int((h_byte << 8) | l_byte)
                        samples.append(atn)                      
                        if file=='ON':
                            if wav:    
                                wavsamp+=struct.pack('>h', atn)
                                if filter:
                                    ws.append(atn)
                                if len(wavsamp)==(framerate):
                                    if filter:
                                        out=fsk_attempt(ws)
                                        wavsamp=struct.pack('>'+'h'*len(ws), *out)
                                    o_f.writeframesraw(wavsamp)
                                    wavsamp = ''
                                    ws=[]
                            else:
                                if not ser2:
                                    o_f.write(struct.pack('h', atn))              
                if len(samples) == spb:
                    bb = 0;
                    for x in range(0, spb, samplesize): 
                        avg = sum(samples[x:x+samplesize]) / spb
                        if (avg>his):
                            his=avg
                        if (avg<los):
                            los=avg
                        bb = (bb << (level / 2)) + data_slice(avg, level=level)
                    if ser2:
                        ser2.write(struct.pack('B', bb))
                        if file=='ON':
                            if not wav:
                                o_f.write(struct.pack('B', bb))
                    samples = []
                    if not dump:        
                        print '{0:>18}'.format(elapsed),
                        print '{0:>18}'.format('-'.join([str(level),'level'])),
                        print '{0:>18}'.format(' - '.join([str(los),str(config['rd_threshold']),str(his)])),                             
                        print '{0:>18}\r'.format('{0:08b}'.format(bb)),
                        sys.stdout.flush()
                    else:
                        textfilter = ''.join([['.', chr(x)][chr(x) in string.printable[:-5]] for x in xrange(256)])
                        hexdump.append(bb)
                        if len(hexdump)==8:
                            for char in hexdump:
                                if strfmt=='text':
                                    print chr(char).translate(textfilter),
                                elif strfmt in DUMP_FMT:
                                    print DUMP_FMT[strfmt].format(char),
                                else:
                                    print DUMP_FMT['hex'].format(char),
                            print
                            sys.stdout.flush()
                            hexdump=[]
            if len(input)==0:
                check_time=int(time.time())
                if (check_time - lread_time) > timeout:
                    print
                    print
                    logging.warning('Null input counter exceeded.')
                    break
                    
            if record_time:
                check_time=int(time.time())
                if (check_time - start_time) > record_time:
                    print
                    print
                    logging.warning('Recording time limit reached.')
                    break
        except KeyboardInterrupt:
            print
            print
            logging.warning('Raw mode aborted.')
            break
    if file=='ON':
        o_f.close()
    if wavinput:
        i_f.close()
    else:
        logging.debug('CMD : Stop Raw Mode')
        ser1.write(command('RMT','SFREQ','STOP'))
        time.sleep(1)
        ser1.flushInput()

def version_string(program=defs.PROGRAM, version=defs.VERSION):
    return ' '.join([program, version]) 

def banner():
    print
    HP_CMD().onecmd('version')
    print
    sys.stdout.flush()

def version_check():
    if config['update_check'] > 0:
        update=None
        doy=int(fn_dt(datetime.datetime.now(), format='%j'))
        if doy % config['update_check']==0:
            print 'Checking for updates...',
            import urllib2
            try:
                request = urllib2.Request(defs.UPDATE_CHECK, headers={'User-Agent' : version_string()}) 
                response = urllib2.urlopen(request).read()
                update=json.loads(response)
            except Exception as detail:  
                print
                logging.error(detail)
                update=None
        if update:
            if update['version'] != defs.VERSION:
                print ' '.join([version_string(version=update['version']), 'is available.'])
            else:
                print ' '.join([defs.PROGRAM, 'is up-to-date.'])
        print

def check_path(path, filename):
    if not os.path.isdir(path):
        try:
            os.makedirs(path)
        except:
            pass
    return os.path.join(path, filename)

def save_config(set=defs.PROGRAM):    
    if set=='':
        set=defs.PROGRAM
    cfgfilename = check_path(config['cfg_path'], '.'.join([defs.PROGRAM,'cfg']))
    Config = ConfigParser.RawConfigParser(config,allow_no_value=True)    
    try:
        Config.read(cfgfilename)
    except:
        logging.warning('Config file not found.')   
    config['config_sets']=list(Config.sections())
    if not Config.has_section(set):
        try:
            Config.add_section(set)
        except:
            logging.error('Invalid set name.')
            return
    Config.set(set,'; ------------ edit with caution ------------')
    for key in OK_VAR:
        Config.set(set,key,config[key])
    cfgfile = open(cfgfilename,'w') 
    Config.write(cfgfile)
    cfgfile.close()
    config['config_name'] = set
    ok()

def load_config(set=defs.PROGRAM, check_only=False):    
    if set=='':
        set=defs.PROGRAM
    cfgfilename = check_path(config['cfg_path'], '.'.join([defs.PROGRAM,'cfg']))
    Config = ConfigParser.RawConfigParser(config,allow_no_value=True)
    try:
        Config.read(cfgfilename)
    except:
        logging.error('Config file not found.')
        return
    config['config_sets']=list(Config.sections())
    if not check_only:
        try:
            for key in OK_VAR:
                set_config(key, Config.get(set,key), verbose=False)
        except ConfigParser.Error:
            logging.error('Config set not found.')
            return
        config['config_name'] = set
        ok()
    
def set_log():
    terminal=os.isatty(0)
    if config['log_file'] == 'ON':   
        try:
            logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                        filename=check_path(config['log_path'],'.'.join([fn_dt(datetime.datetime.now(), config['dateformat']),'log'])),
                        filemode='w')
            console = logging.StreamHandler()
            console.setLevel(config['loglevel'])
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            console.setFormatter(formatter)
            logging.getLogger('').addHandler(console)
        except IOError as detail:
            print
            logging.basicConfig(level=config['loglevel'],format='%(levelname)s: %(message)s')
            logging.error(detail)
    else:
        logging.basicConfig(level=config['loglevel'],format='%(levelname)s: %(message)s')

def parse_arguments():
    parser = argparse.ArgumentParser(description=defs.DESCRIPTION, prog=defs.PROGRAM, usage='%(prog)s [options]', fromfile_prefix_chars='@')
    parser.add_argument('--set', nargs='*', metavar='option=value')
    args, unknown = parser.parse_known_args()
    if args.set:
        for set_cmd in args.set:
            HP_CMD().onecmd(' '.join(['set', set_cmd]))
        print

def console_check():
    if hasattr(sys, "frozen"):
        logging.debug(sys.frozen)
        return sys.frozen=='console_exe' and True or False
    else:
        return True
    
if __name__ == '__main__':

    ser1=None
    ser2=None
    serin=''
    his=50
    los=50
    last_system=None
    display_system=None
    timer=0
    globals=None
    httpd=None
    volsql={}
    favorites={}
        
    config = {
    'port1': 'AUTO',
    'port2': None,
    'rd_freq': 131550000,
    'rd_file': 'OFF',
    'rd_sample': 16,
    'rd_threshold' : 64,
    'rd_path': os.path.abspath(os.path.expanduser(''.join(['~',os.sep,defs.PROGRAM,os.sep,'raw']))), 
    'rd_mode':'AUTO',
    'rd_att' : 'OFF',
    'rd_filter' : 'OFF',
    'rd_timeout' : 3,
    'rd_rectime' : 0,
    'rd_level': 2,
    'rd_input': None,
    'feed_loop' : 'OFF',
    'feed_path' : os.path.abspath(os.path.expanduser(''.join(['~',os.sep,defs.PROGRAM,os.sep,'feeds']))),
    'feed_delay' : 4000,
    'port1_baud' : 115200,
    'port2_baud' : 19200,
    'loglevel' : logging.INFO,
    'log_file' : 'OFF',
    'log_path' : os.path.abspath(os.path.expanduser(''.join(['~',os.sep,defs.PROGRAM,os.sep,'logs']))),
    'dateformat' : '%Y-%m-%d_%H-%M-%S',
    'mon_format' : '%(channel)%,%(system)%,%(department)%',
    'mon_file' : 'OFF',
    'mon_expire' : 0,
    'mon_path' : os.path.abspath(os.path.expanduser(''.join(['~',os.sep,defs.PROGRAM,os.sep,'monitor']))),
    'mon_cmd' : 'ON',
    'cfg_path' : os.path.abspath(os.path.expanduser(''.join(['~',os.sep,defs.PROGRAM]))),
    'web' : 'OFF',
    'web_host' : '',
    'web_port' : 8000,
    'web_readonly' : 'OFF',
    'web_browser' : 'ON',
    'web_ip' : None,
    'web_check' : 0,
    'update_check' : 0,
    'ajax_refresh' : 200,
    'ajax_debug' : False,
    'cmd' : None,
    'hp_model' : None,
    'hp_firmware' : None,
    'hp_database' : None,
    'debug_file' : None,
    'config_name' : None,
    'config_sets' : None,
    }
    
    banner()
    set_log()
    #version_check()
    parse_arguments()

if console_check():
    try:
        HP_CMD().cmdloop()
    except KeyboardInterrupt:
        print
    except Exception as detail:  
        logging.error(detail)
    finally:
        HP_CMD().onecmd('bye')
else:
    HP_CMD().onecmd('web')
    #util.windowsMessageBox(defs.PROGRAM, version_string())