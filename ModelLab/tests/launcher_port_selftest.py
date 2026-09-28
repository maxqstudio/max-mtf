from __future__ import annotations
import socket
from ui.ui_launcher import _free_streamlit_port

def main():
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    try:
        # Test a bounded range where first port is occupied and second is free.
        p=_free_streamlit_port(port,port+1)
        assert p==port+1,(port,p)
    finally:
        s.close()
    src=open('ui_launcher.py',encoding='utf-8').read()
    assert 'Port 8501 sedang dipakai' in src and '--server.port={port}' in src
    print('LAUNCHER_PORT_FALLBACK_SELFTEST PASS')
if __name__=='__main__': main()
