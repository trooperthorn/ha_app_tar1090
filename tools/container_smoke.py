"""Exercise real container processes; no radio receiver or privileged mode."""
import json
import os
from pathlib import Path
import subprocess
import time

def run(*args,check=True):
    return subprocess.run(args,check=check,capture_output=True,text=True)

name='ha-tar1090-smoke'
options=Path('work/smoke-options.json').resolve()
options.parent.mkdir(exist_ok=True)
options.write_text(json.dumps({'source_url':'http://127.0.0.1:1'}))
try:
    security = ['--security-opt','apparmor='+os.environ['APPARMOR_PROFILE']] if os.environ.get('APPARMOR_PROFILE') else []
    run('docker','run','-d','--name',name,*security,'-v',f'{options}:/data/options.json:ro','ha-tar1090:test')
    for attempt in range(30):
        r=run('docker','exec',name,'wget','-qO-','http://127.0.0.1:8098/health',check=False)
        if r.returncode==0: break
        time.sleep(1)
    assert r.returncode==0,run('docker','logs',name).stdout
    run('docker','exec',name,'nginx','-t')
    status=json.loads(run('docker','exec',name,'wget','-qO-','http://127.0.0.1:8098/status.json').stdout)
    assert status['state']=='waiting'
    # The ingress listener must deny a caller outside the Supervisor address.
    denied=run('docker','exec',name,'wget','-S','-O','/dev/null','http://127.0.0.1:8099/',check=False)
    assert '403' in denied.stderr,denied.stderr
    # Remote receiver outage must not terminate/restart the app.
    time.sleep(8)
    assert run('docker','inspect',name,'--format','{{.State.Running}}').stdout.strip()=='true'
    run('docker','stop','--time','15',name)
    assert run('docker','inspect',name,'--format','{{.State.ExitCode}}').stdout.strip()=='0'
    print('container startup, source-outage health, ingress restriction and shutdown passed')
finally:
    run('docker','rm','-f',name,check=False)
