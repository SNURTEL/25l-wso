import sys
import time

import libvirt

iso_path = "/home/tomek/Pobrane/alpine-standard-3.21.3-x86_64.iso"

domain_xml = f"""<domain type='kvm'>
  <name>demo2</name>
  <memory>2097152</memory>
  <vcpu>2</vcpu>
  <os>
    <type arch="i686">hvm</type>
  </os>
  <clock sync="localtime"/>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <source file='{iso_path}'/>
      <target dev='hda'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
    </interface>
    <graphics type='vnc' port='-1' keymap='de'/>
  </devices>
</domain>
"""


def main():
    try:
        conn = libvirt.open("qemu:///system")
    except libvirt.libvirtError:
        print("Failed to open connection to the hypervisor")
        sys.exit(1)

    dom = conn.createXML(domain_xml)
    try:
        if not dom:
            raise SystemExit("Failed to create a domain from an XML definition")

        print("Guest " + dom.name() + " has booted")
        while dom.state() != libvirt.VIR_DOMAIN_SHUTDOWN:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if dom:
            dom.destroy()
            print("Guest " + dom.name() + " terminated")
        conn.close()


if __name__ == "__main__":
    main()
