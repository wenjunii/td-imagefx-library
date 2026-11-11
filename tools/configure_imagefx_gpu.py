"""Opt-in, per-application Windows GPU preference; never changes global GPUs."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,action='append',required=True)
    parser.add_argument('--apply',action='store_true',help='Write High performance for only the listed executables')
    parser.add_argument('--backup',type=Path,help='Required new backup file when applying')
    args=parser.parse_args()
    if sys.platform!='win32': parser.error('Windows only')
    import winreg
    apps=[str(p.resolve()) for p in args.app]
    if any(not Path(p).is_file() or Path(p).suffix.lower()!='.exe' for p in apps):
        parser.error('Every app must be an existing .exe')
    if args.apply and (not args.backup or args.backup.exists()):
        parser.error('--apply requires a new --backup file')
    key_path=r'Software\Microsoft\DirectX\UserGpuPreferences'
    previous={}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,key_path) as key:
            for app in apps:
                try:
                    value,kind=winreg.QueryValueEx(key,app); previous[app]={'value':value,'kind':kind}
                except FileNotFoundError: previous[app]=None
    except FileNotFoundError: previous={app:None for app in apps}
    report={'key':'HKCU\\'+key_path,'previous':previous,'requested':'GpuPreference=2;'}
    if args.apply:
        args.backup.parent.mkdir(parents=True,exist_ok=True)
        with args.backup.open('x',encoding='utf-8') as f:
            json.dump(dict(report,created=datetime.now().isoformat()),f,indent=2)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,key_path) as key:
            for app,old in previous.items():
                # Preserve unrelated per-application preference fields.
                fields=[s for s in (old['value'] if old else '').split(';') if s and not s.startswith('GpuPreference=')]
                value=';'.join([*fields,'GpuPreference=2'])+';'
                winreg.SetValueEx(key,app,0,winreg.REG_SZ,value)
        report['applied']=True
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
