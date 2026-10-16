"""Resolve the physical location of an installed file on packaged Windows apps."""
import os
from pathlib import Path


def runtime_cache():
    """Per-user application cache; never persist one developer's machine path."""
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))
    else:
        base = Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))
    return base/'CodeDuo/runtime'


def physical_file(path):
    path = Path(path)
    if os.name != 'nt':
        return path.resolve()
    import ctypes
    import msvcrt
    function = ctypes.windll.kernel32.GetFinalPathNameByHandleW
    function.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong]
    function.restype = ctypes.c_ulong
    with path.open('rb') as handle:
        buffer = ctypes.create_unicode_buffer(32768)
        size = function(msvcrt.get_osfhandle(handle.fileno()), buffer, len(buffer), 0)
        if not size or size >= len(buffer):
            raise OSError('Cannot resolve installed runtime file')
    value = buffer.value
    if value.startswith('\\\\?\\UNC\\'):
        value = '\\\\' + value[8:]
    elif value.startswith('\\\\?\\'):
        value = value[4:]
    return Path(value)
