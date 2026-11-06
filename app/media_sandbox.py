"""Linux-only unprivileged Landlock filesystem policy and seccomp network denial.
Executed in a fresh, credential-free child before exec; no unsafe preexec_fn in web threads.
"""
import ctypes
import errno
import os
from pathlib import Path
import platform
import resource
import sys


def restrict(workdir):
    if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'aarch64'):
        raise RuntimeError('Audio isolation requires Linux x86_64/aarch64 and Landlock ABI 3 or newer.')
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.syscall(444,0,0,1)<3:
        raise RuntimeError('Landlock ABI 3 or newer is required; processing was not started.')
    if libc.prctl(38,1,0,0,0):raise OSError(ctypes.get_errno(),'no_new_privs failed')
    class Ruleset(ctypes.Structure):
        _fields_=[('handled_access_fs',ctypes.c_uint64)]
    class Beneath(ctypes.Structure):
        _fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int32)]
    rights=(1<<15)-1  # ABI 3 filesystem rights, including REFER and TRUNCATE.
    attr=Ruleset(rights)
    fd=libc.syscall(444,ctypes.byref(attr),ctypes.sizeof(attr),0)
    if fd<0:raise OSError(ctypes.get_errno(),'Landlock ruleset failed')
    try:
        # Runtime libraries/executable only; no /srv/app, /data, /proc, home or private /etc files.
        paths=[('/usr',13),('/lib',13),('/lib64',13),('/etc/ld.so.cache',4),('/dev/null',6),('/dev/urandom',4),(str(workdir),rights)]
        for name,allowed in paths:
            if not Path(name).exists():continue
            parent=os.open(name,os.O_PATH|os.O_CLOEXEC)
            try:
                rule=Beneath(allowed,parent)
                if libc.syscall(445,fd,1,ctypes.byref(rule),0):raise OSError(ctypes.get_errno(),'Landlock rule failed')
            finally:os.close(parent)
        if libc.syscall(446,fd,0):raise OSError(ctypes.get_errno(),'Landlock enforcement failed')
    finally:os.close(fd)
    sec=ctypes.CDLL('libseccomp.so.2')
    sec.seccomp_init.argtypes=[ctypes.c_uint32];sec.seccomp_init.restype=ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];sec.seccomp_syscall_resolve_name.restype=ctypes.c_int
    sec.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    sec.seccomp_load.argtypes=[ctypes.c_void_p];sec.seccomp_release.argtypes=[ctypes.c_void_p]
    context=sec.seccomp_init(0x7fff0000)
    if not context:raise RuntimeError('seccomp initialization failed')
    try:
        for name in ('socket','socketpair','connect','bind','listen','accept','accept4','sendto','recvfrom','sendmsg','recvmsg','sendmmsg','recvmmsg','ptrace','process_vm_readv','process_vm_writev','io_uring_setup','unshare','setns','mount','open_by_handle_at','keyctl','bpf'):
            number=sec.seccomp_syscall_resolve_name(name.encode())
            if number>=0 and sec.seccomp_rule_add(context,0x00050000|errno.EPERM,number,0):raise RuntimeError('seccomp rule failed')
        if sec.seccomp_load(context):raise RuntimeError('seccomp enforcement failed')
    finally:sec.seccomp_release(context)
    for limit,value in ((resource.RLIMIT_CPU,240),(resource.RLIMIT_AS,768*1024**2),(resource.RLIMIT_FSIZE,256*1024**2),(resource.RLIMIT_NOFILE,64),(resource.RLIMIT_CORE,0)):
        resource.setrlimit(limit,(value,value))


if __name__=='__main__':
    try:
        workdir=Path(sys.argv[1]).resolve(strict=True)
        os.chdir(workdir)
        restrict(workdir)
        os.execv(sys.argv[2],sys.argv[2:])
    except Exception:
        print('Audio isolation could not be enforced; processing was not started.',file=sys.stderr)
        sys.exit(125)
