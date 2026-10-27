"""Install the local user timer; no browser session is needed."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
units = Path.home()/'.config/systemd/user'
units.mkdir(parents=True, exist_ok=True)
def quoted(path):
    return '"' + str(path).replace('%', '%%').replace('\\', '\\\\').replace('"', '\\"') + '"'
(units/'fabrica-resume.service').write_text(f'''[Unit]
Description=Retomada de producoes da Fabrica
[Service]
Type=oneshot
WorkingDirectory={str(root).replace('%', '%%')}
ExecStart={quoted(root/'.venv/bin/python')} -m app.services.production.resume
TimeoutStartSec=infinity
''')
(units/'fabrica-resume.timer').write_text('''[Unit]
Description=Verificar producoes salvas a cada minuto
[Timer]
OnCalendar=*-*-* *:*:00
Persistent=true
[Install]
WantedBy=timers.target
''')
subprocess.run(['systemctl','--user','daemon-reload'], check=True)
subprocess.run(['systemctl','--user','enable','--now','fabrica-resume.timer'], check=True)
