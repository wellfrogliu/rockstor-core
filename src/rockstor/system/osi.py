"""
Copyright (c) 2012-2013 RockStor, Inc. <http://rockstor.com>
This file is part of RockStor.

RockStor is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published
by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

RockStor is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import re
import os
import subprocess
import shutil
from tempfile import mkstemp
import time
from socket import inet_ntoa
from struct import pack
from exceptions import CommandException
import logging
logger = logging.getLogger(__name__)


HOSTS_FILE = '/etc/hosts'
MKDIR = '/bin/mkdir'
RMDIR = '/bin/rmdir'
CHMOD = '/bin/chmod'
MOUNT = '/bin/mount'
UMOUNT = '/bin/umount'
EXPORTFS = '/usr/sbin/exportfs'
RESTART = '/sbin/restart'
SERVICE = '/sbin/service'
HOSTID = '/usr/bin/hostid'
IFCONFIG = '/sbin/ifconfig'
LVS = '/sbin/lvs'
VGS = '/sbin/vgs'
IFUP = '/sbin/ifup'
IFDOWN = '/sbin/ifdown'
ROUTE = '/sbin/route'
DEFAULT_MNT_DIR = '/mnt2/'
SHUTDOWN = '/usr/sbin/shutdown'
GRUBBY = '/usr/sbin/grubby'
CAT = '/usr/bin/cat'
UDEVADM = '/usr/sbin/udevadm'
GREP = '/usr/bin/grep'
NMCLI = '/usr/bin/nmcli'


def inplace_replace(of, nf, regex, nl):
    with open(of) as afo, open(nf, 'w') as tfo:
        replaced = [False, ] * len(regex)
        for l in afo.readlines():
            ireplace = False
            for i in range(0, len(regex)):
                if (re.match(regex[i], l) is not None):
                    tfo.write(nl[i])
                    replaced[i] = True
                    ireplace = True
                    break
            if (not ireplace):
                tfo.write(l)
        for i in range(0, len(replaced)):
            if (not replaced[i]):
                tfo.write(nl[i])


def run_command(cmd, shell=False, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, throw=True, log=False):
    p = subprocess.Popen(cmd, shell=shell, stdout=stdout, stderr=stderr)
    out, err = p.communicate()
    out = out.split('\n')
    err = err.split('\n')
    rc = p.returncode
    if (rc != 0):
        if (log):
            e_msg = ('non-zero code(%d) returned by command: %s. output: %s error:'
                     ' %s' % (rc, cmd, out, err))
            logger.error(e_msg)
        if (throw):
            raise CommandException(cmd, out, err, rc)
    return (out, err, rc)


def uptime():
    with open('/proc/uptime') as ufo:
        return int(float(ufo.readline().split()[0]))


def def_kernel():
    kernel = None
    o, e, rc = run_command([GRUBBY, '--default-kernel'], throw=False)
    if (len(o) > 0):
        k_fields = o[0].split('/boot/vmlinuz-')
        if (len(k_fields) == 2):
            kernel = k_fields[1]
    return kernel


def kernel_info(supported_version):
    uname = os.uname()
    if (uname[2] != supported_version):
        e_msg = ('You are running an unsupported kernel(%s). Some features '
                 'may not work properly.' % uname[2])
        run_command([GRUBBY, '--set-default=/boot/vmlinuz-%s' % supported_version])
        e_msg = ('%s Please reboot and the system will '
                 'automatically boot using the supported kernel(%s)' %
                 (e_msg, supported_version))
        raise Exception(e_msg)
    return uname[2]


def create_tmp_dir(dirname):
    return run_command([MKDIR, '-p', dirname])


def rm_tmp_dir(dirname):
    return run_command([RMDIR, dirname])


def nfs4_mount_teardown(export_pt):
    """
    reverse of setup. cleanup when there are no more exports
    """
    if (is_mounted(export_pt)):
        run_command([UMOUNT, '-l', export_pt])
        for i in range(10):
            if (not is_mounted(export_pt)):
                return run_command([RMDIR, export_pt])
            time.sleep(1)
        run_command([UMOUNT, '-f', export_pt])
    if (os.path.exists(export_pt)):
        return run_command([RMDIR, export_pt])
    return True


def bind_mount(mnt_pt, export_pt):
    if (not is_mounted(export_pt)):
        run_command([MKDIR, '-p', export_pt])
        run_command([CHMOD, '-R', '777', export_pt])
        return run_command([MOUNT, '--bind', mnt_pt, export_pt])
    return True


def refresh_nfs_exports(exports):
    """
    input format:

    {'export_point': [{'client_str': 'www.example.com',
                       'option_list': 'rw,insecure,'
                       'mnt_pt': mnt_pt,},],
                       ...}

    if 'clients' is an empty list, then unmount and cleanup.
    """
    fo, npath = mkstemp()
    with open(npath, 'w') as efo:
        shares = []
        for e in exports.keys():
            if (len(exports[e]) == 0):
                #  do share tear down at the end, only snaps here
                if (len(e.split('/')) == 4):
                    nfs4_mount_teardown(e)
                else:
                    shares.append(e)
                continue

            if (not is_mounted(e)):
                bind_mount(exports[e][0]['mnt_pt'], e)
            client_str = ''
            admin_host = None
            for c in exports[e]:
                run_command([EXPORTFS, '-i', '-o', c['option_list'],
                             '%s:%s' % (c['client_str'], e)])
                client_str = ('%s%s(%s) ' % (client_str, c['client_str'],
                                             c['option_list']))
                if ('admin_host' in c):
                    admin_host = c['admin_host']
            if (admin_host is not None):
                run_command([EXPORTFS, '-i', '-o', 'rw,no_root_squash',
                             '%s:%s' % (admin_host, e)])
                client_str = ('%s %s(rw,no_root_squash)' % (client_str,
                                                            admin_host))
            export_str = ('%s %s\n' % (e, client_str))
            efo.write(export_str)
        for s in shares:
            nfs4_mount_teardown(s)
    shutil.move(npath, '/etc/exports')
    return run_command([EXPORTFS, '-ra'])


def hostid():
    """
    return the hostid of the machine
    """
    return run_command([HOSTID])


def restart_network():
    """
    restart network service
    """
    cmd = [SERVICE, 'network', 'restart']
    return run_command(cmd)


def restart_network_interface(iname):
    """
    ifdown followed by ifup of a ethernet interface
    """
    run_command([IFDOWN, iname])
    return run_command([IFUP, iname])


def network_devices():
    """
    return all network devices on the system. @todo: this logic needs to mature
    over all.
    """
    ifpath = '/sys/class/net'
    devices = []
    dvirt = os.path.join(ifpath, 'docker0')
    docker = False
    if (os.path.exists(dvirt)):
        docker = True
    for n in os.listdir(ifpath):
        fp = os.path.join(ifpath, n)
        if (os.path.isdir(fp)):
            #ignore files. nic bonding creates a file called bonding_masters,
            #for example.

            #ignore loopback device
            #ignore docker virt interface
            if (n == 'lo'):
                continue
            if (n == 'docker0'):
                continue

            #ignore all docker virt interfaces.
            master = os.path.join(fp, 'master')
            if (os.path.exists(master) and
                docker is True and
                os.path.samefile(master, dvirt)):
                continue

            devices.append(n)
    return devices


def get_mac_addr(interface):
    """
    return the mac address of the given interface
    """
    ifile = ('/sys/class/net/%s/address' % interface)
    with open(ifile) as ifo:
        return ifo.readline().strip()


def get_default_interface():
    """
    returns the interface configured with default gateway
    """
    out, err, rc = run_command([ROUTE])
    for line in out:
        fields = line.split()
        if (len(fields) > 0 and fields[0] == 'default'):
            return fields[-1]
    return None


def get_ip_addr(interface):
    """
    useful when the interface gets ip from a dhcp server
    """
    out, err, rc = run_command([IFCONFIG, interface])
    if (len(out) > 1):
        line2 = out[1].strip()
        if (re.match('inet ', line2) is not None):
            fields = line2.split()
            if (len(fields) > 1):
                return line2.split()[1]
    return '0.0.0.0'


def config_network_device(name, boot_proto='dhcp', ipaddr=None,
                          netmask=None, auto_connect='yes', gateway=None,
                          dns_servers=None):
    #1. delete the existing connection
    show_cmd = [NMCLI, 'c', 'show', name]
    o, e, rc = run_command(show_cmd, throw=False)
    if (rc == 0):
        run_command([NMCLI, 'c', 'delete', name])
    elif (rc != 0 and rc != 10):
        #unknown error
        e_msg = ('Unexpected error while running command: %s. out: %s err: '
                 '%s' % (show_cmd, o, e))
        raise Exception(e_msg)
    #2. Add a new connection
    add_cmd = [NMCLI, 'c', 'add', 'type', dtype, 'con-name', name, 'ifname', name]
    if (boot_proto != 'dhcp'):
        add_cmd.extend(['ip4', '%s/%s' % (ipaddr, netmask)])
    if (gateway is not None):
        add_cmd.extend(['gw4', gateway])
    run_command(add_cmd)
    #3. modify with extra options like dns servers
    mod_cmd = [NMCLI, 'c', 'mod']
    if (dns_servers is not None):
        mod_cmd.extend(['ipv4.dns', dns_servers])
    if (auto_connect == 'no'):
        mod_cmd.extend(['connection.auto_connect', 'no'])
    run_command(mod_cmd)


def char_strip(line, char='"'):
    if (line[0] == char and line[-1] == char):
        return line[1:-1]
    return line


def parse_ifcfg(config_file, config_d):
    try:
        with open(config_file) as cfo:
            dns_servers = []
            for l in cfo.readlines():
                if (re.match('BOOTPROTO', l) is not None):
                    config_d['bootproto'] = char_strip(l.strip().split('=')[1])
                elif (re.match('ONBOOT', l) is not None):
                    config_d['onboot'] = char_strip(l.strip().split('=')[1])
                elif (re.match('IPADDR', l) is not None):
                    config_d['ipaddr'] = char_strip(l.strip().split('=')[1])
                elif (re.match('NETMASK', l) is not None):
                    config_d['netmask'] = char_strip(l.strip().split('=')[1])
                elif (re.match('NETWORK', l) is not None):
                    config_d['network'] = char_strip(l.strip().split('=')[1])
                elif (re.match('NAME', l) is not None):
                    config_d['alias'] = char_strip(l.strip().split('=')[1])
                elif (re.match('GATEWAY', l) is not None):
                    config_d['gateway'] = char_strip(l.strip().split('=')[1])
                elif (re.match('DNS', l) is not None):
                    dns_servers.append(char_strip(l.strip().split('=')[1]))
                elif (re.match('DOMAIN', l) is not None):
                    config_d['domain'] = char_strip(l.strip().split('=')[1])
            if (len(dns_servers) > 0):
                config_d['dns_servers'] = ','.join(dns_servers)
    except:
        pass
    finally:
        if (config_d['bootproto'] != 'static'):
            config_d['ipaddr'] = get_ip_addr(config_d['name'])
        return config_d

def convert_netmask(bits):
    #convert netmask bits into ip representation
    bits = int(bits)
    mask = 0
    for i in xrange(32-bits,32):
        mask |= (1 << i)
    return inet_ntoa(pack('>I', mask))

def net_config_helper(name):
    config = {}
    o, e, rc = run_command([NMCLI, '-t', 'c', 'show', name], throw=False)
    if (rc == 10):
        return config
    for l in o:
        l = l.strip()
        if ('method' in config):
            if (config['method'] == 'auto'):
                #dhcp
                if (re.match('DHCP4.OPTION.*ip_address = .+', l) is not None):
                    config['ipaddr'] = l.split('= ')[1]
                elif (re.match('DHCP4.OPTION.*domain_name_servers = .+', l) is not None):
                    config['dns_servers'] = l.split('= ')[1]
                elif (re.match('DHCP4.OPTION.*subnet_mask = .+', l) is not None):
                    config['netmask'] = l.split('= ')[1]
                elif (re.match('IP4.GATEWAY:.+', l) is not None):
                    config['gateway'] = l.split(':')[1]

            elif (config['method'] == 'manual'):
                #manual
                if (re.match('IP4.ADDRESS', l) is not None):
                    kv_split = l.split(':')
                    if (len(kv_split) > 1):
                        vsplit = kv_split[1].split('/')
                    if (len(vsplit) > 0):
                        config['ipaddr'] = vsplit[0]
                    if (len(vsplit) > 1):
                        config['netmask'] = convert_netmask(vsplit[1])
                elif (re.match('ipv4.dns:.+', l) is not None):
                    config['dns_servers'] = l.split(':')[1]
                elif (re.match('ipv4.gateway:.+', l) is not None):
                    config['gateway'] = l.split(':')[1]

            else:
                raise Exception('Unknown ipv4.method(%s). ' % config['method'])

        if (re.match('connection.interface-name:', l) is not None):
            config['name'] = l.split(':')[1]
        elif (re.match('connection.autoconnect:', l) is not None):
            config['autoconnect'] = l.split(':')[1]
        elif (re.match('ipv4.method:.+', l) is not None):
            config['method'] = l.split(':')[1]

        if (re.match('GENERAL.DEVICES:.+', l) is not None):
            config['dname'] = l.split(':')[1]
        elif (re.match('connection.type:.+', l) is not None):
            config['ctype'] = l.split(':')[1]
        elif (re.match('GENERAL.STATE:.+', l) is not None):
            config['state'] = l.split(':')[1]

    if ('dname' in config):
        o, e, rc = run_command([NMCLI, '-t', '-f', 'all', 'd', 'show', config['dname'],])
        for l in o:
            l = l.strip()
            if (re.match('GENERAL.TYPE:.+', l) is not None):
                config['dtype'] = l.split(':')[1]
            elif (re.match('GENERAL.HWADDR:.+', l) is not None):
                config['mac'] = l.split('GENERAL.HWADDR:')[1]
            elif (re.match('CAPABILITIES.SPEED:.+', l) is not None):
                config['dspeed'] = l.split(':')[1]

    return config

def get_net_config(all=False, name=None):
    if (all):
        o, e, rc = run_command([NMCLI, '-t', 'd', 'show'])
        devices = []
        for i in range(len(o)):
            if (re.match('GENERAL.DEVICE:', o[i]) is not None and
                re.match('GENERAL.TYPE:', o[i+1]) is not None and
                o[i+1].strip().split(':')[1] == 'ethernet'):
                devices.append(o[i].strip().split(':')[1])
        config = {}
        for d in devices:
            config[d] = net_config_helper(d)
        return config
    return {name: net_config_helper(name),}


def set_networking(hostname, default_gw):
    with open('/etc/sysconfig/network', 'w') as nfo:
        nfo.write('NETWORKING=yes\n')
        nfo.write('HOSTNAME=%s\n' % hostname)
        nfo.write('GATEWAY=%s\n' % default_gw)


def set_nameservers(servers):
    with open('/etc/resolv.conf', 'w') as rfo:
        for s in servers:
            rfo.write('nameserver %s\n' % s)


def update_issue(ipaddr):
    shutil.copyfile('/etc/issue.rockstor', '/etc/issue')
    msg = ("\n\nYou can go to RockStor's webui by pointing your web browser"
           " to https://%s\n\n" % ipaddr)
    with open('/etc/issue', 'a') as ifo:
        ifo.write(msg)


def sethostname(ip, hostname):
    """
    edit /etc/hosts file and /etc/hostname
    """
    fh, npath = mkstemp()
    with open(HOSTS_FILE) as hfo, open(npath, 'w') as tfo:
        for line in hfo.readlines():
            if (re.match(ip, line) is None):
                tfo.write(line)
        tfo.write('%s %s\n' % (ip, hostname))
    shutil.move(npath, HOSTS_FILE)
    os.chmod(HOSTS_FILE, 0644)

    with open('/etc/hostname', 'w') as hnfo:
        hnfo.write('%s\n' % hostname)


def is_share_mounted(sname, mnt_prefix=DEFAULT_MNT_DIR):
    mnt_pt = mnt_prefix + sname
    return is_mounted(mnt_pt)


def is_mounted(mnt_pt):
    with open('/proc/mounts') as pfo:
        for line in pfo.readlines():
            if (re.search(' ' + mnt_pt + ' ', line) is not None):
                return True
    return False


def get_disk_serial(device_name, test):
    """
    Returns the serial number of device_name using udevadm to match that
    returned by lsblk. N.B. udevadm has been observed to return the following:-
    ID_SCSI_SERIAL  rarely seen
    ID_SERIAL_SHORT  often seen
    ID_SERIAL        thought to always be seen (see note below)
    N.B. if used in this order the serial is most likely to resemble that shown
    on the device label as well as that returned by the lsblk. ID_SERIAL seems
    always to appear but is sometimes accompanied by one or both of the others.
    When ID_SERIAL is accompanied by ID_SERIAL_SHORT the short variant is
    closer to lsblk and physical label. When they are both present the
    ID_SERIAL appears to be a combination of the model and the ID_SERIAL_SHORT
    :param device_name:
    :param test:
    :return: 12345678901234567890
    """
    # logger.info('get_disk_serial called with device name %s' % device_name)
    serial_num = ''
    line_fields = []
    if test is None:
        out, err, rc = run_command([UDEVADM, 'info', '--name=' + device_name],
                                   throw=False)
    else:
        # test mode so process test instead of udevadmin output
        out = test
        rc = 0
    if rc != 0:  # if return code is an error return empty string
        return ''
    for line in out:
        if line == '':
            continue
        # nonlocal line_fields
        line_fields = line.strip().replace('=', ' ').split()
        # fast replace of '=' with space so split() can divide all fields
        # example original line "E: ID_SERIAL_SHORT=S1D5NSAF111111K"
        # less than 3 fields are of no use so just in case:-
        if len(line_fields) < 3:
            continue
        if line_fields[1] == 'ID_SCSI_SERIAL':
            # we have an instance of SCSI_SERIAL being more reliably unique
            # when present than SERIAL_SHORT or SERIAL so overwrite whatever
            # we have and look no further by breaking out of the search loop
            serial_num = line_fields[2]
            break
        elif line_fields[1] == 'ID_SERIAL_SHORT':
            # SERIAL_SHORT is better than SERIAL so just overwrite whatever we
            # have so far with SERIAL_SHORT
            serial_num = line_fields[2]
        else:
            if line_fields[1] == 'ID_SERIAL':
                # SERIAL is sometimes our only option but only use it if we
                # have found nothing else.
                if serial_num == '':
                    serial_num = line_fields[2]
    # should return one of the following in order of priority
    # SCSI_SERIAL, SERIAL_SHORT, SERIAL
    # logger.info('get_disk_serial returning serial # %s' % serial_num)
    return serial_num


def get_virtio_disk_serial(device_name):
    """
    N.B. this function is deprecated by get_disk_serial
    Returns the serial number of device_name virtio disk eg /dev/vda
    Returns empty string if cat /sys/block/vda/serial command fails
    Note no serial entry in /sys/block/sda/ for real or KVM sata drives
    :param device_name: vda
    :return: 12345678901234567890

    Note maximum length of serial number reported = 20 chars
    But longer serial numbers can be specified in the VM XML spec file.
    The virtio block device is itself limited to 20 chars ie:-
    https://github.com/qemu/qemu/blob/
    a9392bc93c8615ad1983047e9f91ee3fa8aae75f/include/standard-headers/
    linux/virtio_blk.h
    #define VIRTIO_BLK_ID_BYTES	20	/* ID string length */

    This process may not deal well with spaces in the serial number
    but VMM does not allow this.
    """
    dev_path = ('/sys/block/%s/serial' % device_name)
    out, err, rc = run_command([CAT, dev_path], throw=False)
    if (rc != 0):
        return ''
    # our out list has one element that is the serial number, like ['11111111111111111111']
    return out[0]


def system_shutdown():
    return run_command([SHUTDOWN, '-h'])


def system_reboot():
    return run_command([SHUTDOWN, '-r'])
