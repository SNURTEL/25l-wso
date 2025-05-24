import nmcli

from wso.config import PHYSICAL_IFACE_NAME, QEMU_BINARY_PATH


def destroy_bridge_iface(name: str):
    nmcli.connection.delete(name)
    nmcli.connection.delete(f"{name}-s")


def get_domain_xml(name: str, n_cpus: int, memory_kib: int, bridge_iface_name: str, iso_path):
    domain_xml = f"""
  <domain type='kvm'>
    <name>{name}</name>
    <memory>{memory_kib}</memory>
    <vcpu>{n_cpus}</vcpu>
    <os>
      <type arch="i686">hvm</type>
    </os>
    <clock sync="localtime"/>
    <devices>
      <emulator>{QEMU_BINARY_PATH}</emulator>
      <disk type='file' device='disk'>
        <source file='{iso_path}'/>
        <target dev='hda'/>
      </disk>
      <interface type='bridge'>
        <source bridge='{bridge_iface_name}'/>
        <model type='virtio'/>
      </interface>
      <graphics type='vnc' port='-1' keymap='de'/>
    </devices>
  </domain>
  """
    return domain_xml


def create_bridge_iface(name: str, physical_iface_name: str = PHYSICAL_IFACE_NAME):
    assert len(name) <= 13

    connection = name
    iface = name

    nmcli.connection.add(name=connection, ifname=iface, conn_type="bridge", autoconnect=True)

    nmcli.connection.add(
        name=f"{connection}-s",
        ifname=physical_iface_name,
        conn_type="bridge-slave",
        options={"master": iface},
        autoconnect=True,
    )

    nmcli.connection.up(connection)
    return {"connection": connection, "iface": iface}
