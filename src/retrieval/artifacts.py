"""Strict JSON artifacts and runtime provenance."""
from datetime import datetime, timezone
import importlib.metadata
import json
import platform
import subprocess


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n')


def environment():
    def system_value(key):
        try:
            return subprocess.check_output(['sysctl','-n',key],text=True,stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.CalledProcessError):
            return 'unavailable'
    return {'python':platform.python_version(),'platform':platform.platform(),'machine':platform.machine(),
            'cpu':system_value('machdep.cpu.brand_string'),'memory_bytes':system_value('hw.memsize'),
            'logical_cpus':system_value('hw.logicalcpu'),
            'dependencies':{d.metadata['Name']:d.version for d in importlib.metadata.distributions()}}
