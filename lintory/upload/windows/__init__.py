from django.http import Http404, HttpResponseForbidden

import os
import datetime
import re

from lintory.views import lintory_root
from lintory import helpers, models
from lintory.upload.windows import hacks

class import_error(Exception):
    def __init__(self, value):
            self.value = value

    def __unicode__(self):
            return repr(self.value)

class computer_does_not_exist(import_error):
    pass

class os_does_not_exist(import_error):
    pass

def upload(request):
    if request.method != "PUT":
        raise Http404("Unsupported request method")

    if request.META["CONTENT_TYPE"] != "text/plain":
        raise Http404("Unsupported content type")

    data = models.data()
    data.datetime = datetime.datetime.now()
    data.file = models.data_upload_to(data, None)
    data.format = "windows"

    path = data.file.path
    tmppath = path + ".tmp"
    print path

    (head,tail) = os.path.split(path)
    if not os.path.exists(head):
        os.makedirs(head)

    file = open(tmppath,"w")
    file.write(request.raw_post_data)
    file.close()
    os.rename(tmppath, path)

    data.save()
    return lintory_root(request)

# Used for stripping non-ascii characters
t = "".join(map(chr, range(256)))
d = "".join(map(chr, range(128,256)))

def parse_file(file):
    data_dict = {}
    sections = [ data_dict ]
    this_section = None

    line = file.readline()
    while line != "":
        # string non-ASCII characters and terminating white space
        line = line.translate(t,d).rstrip()

        if len(line)>0 and line[0] == '#':
            level = 1
            while line[level] == '#':
                level = level + 1
            name = line[level+1:]

            del sections[level:]
            if len(sections) != level:
                raise import_error("Incorrect level found in file")

            this_section = {}

            upper = sections[level-1]
            sections.append(this_section)

            if name not in upper:
                upper[name] = []

            upper[name].append(this_section)

        elif len(sections)<=1:
            # ignore line
            pass
        elif line.find(":") != -1:
            (tag,sep,value) = line.partition(":")
            this_section[tag] = value
        else:
            raise import_error("Cannot parse line")

        line = file.readline()

    if "end" not in data_dict:
        raise import_error("End marker not found in file")

    return data_dict

def is_physical_network_adapter(network_adaptor_data):
    if "PhysicalAdapter" in network_adaptor_data:
        if network_adaptor_data['PhysicalAdapter'] == "True":
            return True
        else:
            return False

    if network_adaptor_data['MACAddress'] == "":
        return False

    if network_adaptor_data['Manufacturer'] == "":
        return False

    if network_adaptor_data['Manufacturer'] == "Microsoft":
        return False

    if network_adaptor_data['Manufacturer'] == "ESET":
        return False

    if network_adaptor_data['Manufacturer'] == "Symantec":
        return False

    if network_adaptor_data['Manufacturer'] == "TAP-Win32 Provider":
        return False

    return True

def get_computer_serial_number(data_dict):
    serial_number = None
    if 'BaseBoard' in data_dict:
        if len(data_dict['BaseBoard']) > 1:
            raise import_error("Multiple BaseBoard found")
        serial_number = son(data_dict['BaseBoard'][0]['SerialNumber'])
    return serial_number

def get_computer(data_dict):
    # Sanity check input data_dict
    if len(data_dict['ComputerSystem']) == 0:
        raise import_error("No ComputerSystem found")

    if len(data_dict['ComputerSystem']) > 1:
        raise import_error("Multipe ComputerSystem found")

    # All search terms must match
    query = models.computer.objects.all()

    # Try finding computer based on serial number
    # note: serial number is not guaranteed to be unique
    serial_number = get_computer_serial_number(data_dict)
    if serial_number is not None:
        new_query = query.filter(auto_serial_number=serial_number)
        if new_query.count() > 0:
            query = new_query
    else:
        query = query.filter(auto_serial_number__isnull=True)

    # Try finding computer based on the name
    computer_name = son(data_dict['ComputerSystem'][0]['Name'])
    if computer_name is not None:
        new_query = query.filter(name = computer_name)
        if new_query.count() > 0:
            query = new_query

    # Try to find computer by MAC addresses. All MAC addresses must match, but
    # only if we already have a record of the MAC address.
    for network in data_dict['NetworkAdapter']:
        if is_physical_network_adapter(network):
            mac_address = helpers.fix_mac_address(network['MACAddress'])
            try:
                na = models.network_adaptor.objects.get(mac_address=mac_address)
                query = query.filter(installed_hardware__network_adaptor=na)
            except models.network_adaptor.DoesNotExist, e:
                pass

    # Check - did we get a valid result?
    count = query.count()
    if count == 0:
        raise computer_does_not_exist("No matching computer found")

    if count > 1:
        raise import_error("Too many matching computers")

    return query[0]

def create_computer(data_datetime):
    c = models.computer()
    c.seen_first = data_datetime
    c.seen_last = data_datetime
    return c

def get_disk_drive_from_id(id, data_dict):
    for disk_drive in data_dict['DiskDrive']:
        if 'DiskPartition' in disk_drive:
            for disk_partition in disk_drive['DiskPartition']:
                if 'LogicalDisk' in disk_partition:
                    for logical_disk in disk_partition['LogicalDisk']:
                        if id == logical_disk['DeviceID']:
                            return disk_drive
    raise import_error("Disk '%s' not found"%(id))

def get_os_storage(computer, data_dict):
    # Sanity check input data_dict
    if len(data_dict['OperatingSystem']) == 0:
        raise import_error("No OperatingSystem found")

    if len(data_dict['OperatingSystem']) > 1:
        raise import_error("Multiple OperatingSystem found")

    # Get the storage device from the WindowsDirectory
    drive = data_dict['OperatingSystem'][0]['SystemDrive']
    disk_drive = get_disk_drive_from_id(drive, data_dict)

    # Get serial number of storage device
    serial_number=None
    if "SerialNumber" in disk_drive:
        serial_number = son(disk_drive['SerialNumber'])

    # Try to find the storage object that the OS is stored on
    # First attempt - assume serial number is trusted!!
    if serial_number is not None:
        try:
            storage = models.storage.objects.get(
                        auto_manufacturer=son(disk_drive['Manufacturer']),
                        auto_model=son(disk_drive['Model']),
                        serial_number=serial_number,
                        total_size=son(disk_drive['TotalSectors']),
                        sector_size=son(disk_drive['BytesPerSector']),
            )
            return storage
        except models.storage.DoesNotExist, e:
            pass

    # Second attempt, we cannot trust serial_number, check drive is marked as
    # in use by this computer too.
    try:
        storage = models.storage.objects.get(
                    used_by=computer,
                    auto_manufacturer=son(disk_drive['Manufacturer']),
                    auto_model=son(disk_drive['Model']),
                    serial_number=serial_number,
                    total_size=son(disk_drive['TotalSectors']),
                    sector_size=son(disk_drive['BytesPerSector']),
        )
        return storage
    except models.storage.DoesNotExist, e:
        pass

    # Didn't work, lets just look for any unmarked drive in use by this
    # computer. Won't work if this returns multiple matches.
    try:
        storage = models.storage.objects.get(
                    used_by=computer,
                    manufacturer__isnull=True,
                    model__isnull=True,
                    serial_number__isnull=True,
        )
        return storage
    except models.storage.DoesNotExist, e:
        pass

    # Maybe we still couldn't find it
    raise import_error("Cannot find storage device for OS '%s'"%(son(data_dict['OperatingSystem'][0]['Caption'])))

def get_os(computer, data_dict):
    # Sanity check input data_dict
    if len(data_dict['OperatingSystem']) == 0:
        raise import_error("No OperatingSystem found")

    if len(data_dict['OperatingSystem']) > 1:
        raise import_error("Multipe OperatingSystem found")

    if data_dict['OperatingSystem'][0]['CSName'] == "":
        raise import_error("No computer name given")

    # Get the (unmangled) OS Name
    name = son(data_dict['OperatingSystem'][0]['Caption'])

    # Get storage device OS is stored on
    storage = get_os_storage(computer, data_dict)

    # Try to find the OS object
    try:
        os = models.os.objects.get(
                    name = name,
                    computer_name = son(data_dict['OperatingSystem'][0]['CSName']),
                    storage = storage,
        )
    except models.os.DoesNotExist, e:
        raise os_does_not_exist("Cannot find OS '%s'"%(name))

    return os

def create_os(data_datetime, computer, data_dict):
    os = models.os()
    os.seen_first = data_datetime
    os.seen_last = data_datetime
    os.storage = get_os_storage(computer, data_dict)
    return os

# return None if string == ""
def son(string):
    if string == "":
        return None
    else:
        return string

# has_changed - update value only if it is different from when we last
# saw it. This allows the user to change the value without having the change
# being overwritten
# auto - the value as we last saw it
# old  - the value the user sees
# new  - the new value the user sees
# paranoid - want to manually inspect changes for testing

def has_changed(auto,old,new,paranoid=True):
    # Were we given a new value?
    if new is None:
        # no -> nothing changed
        return False

    # Is this value different from when we last saw it?
    if auto == new:
        # no -> nothing changed
        return False

    # Do have have an value set already?
    if old is None:
        # no -> assume new value is better then no value
        return True

    # Have we have seen value last time?
    if auto is None:
        # no -> we can't tell - assume no change
        return False

    # Or is this value different?
    if old == new:
        # no -> nothing changed
        return False

    if paranoid:
        # YES! Value needs updating, however we are paranoid
        raise import_error("We are paranoid - not updating '%s' to '%s'"%(old,new))

    # Value needs changing and we somehow managed to get past all the above
    # checks. Weird. No choice but to return the value of ...
    return True

def sync_hardware(data_datetime, computer, data_dict):
    # Update computer details
    computer.name         = son(data_dict['ComputerSystem'][0]['Name'])
    computer.seen_last    = data_datetime
    computer.memory       = son(data_dict['ComputerSystem'][0]['TotalPhysicalMemory'])

    # Update manufacturer, if required
    value = son(data_dict['ComputerSystem'][0]['Manufacturer'])
    if has_changed(computer.auto_manufacturer,computer.manufacturer,value):
        computer.manufacturer = value
    computer.auto_manufacturer = value

    # Update model, if required
    value = son(data_dict['ComputerSystem'][0]['Model'])
    if has_changed(computer.auto_model,computer.model,value):
        computer.model = value
    computer.auto_model = value

    # Try to find the serial number
    serial_number = get_computer_serial_number(data_dict)

    # Update serial number, if required
    if has_changed(computer.auto_serial_number,computer.serial_number,serial_number):
        computer.serial_number = serial_number
    computer.auto_serial_number = serial_number

    # Now do the hardware
    hardware = [ h.pk for h in computer.installed_hardware.all() ]
    used_storage = [ h.pk for h in computer.used_storage.all() ]

    seen_hardware = {}
    for network in data_dict['NetworkAdapter']:
        if is_physical_network_adapter(network):
            mac_address = helpers.fix_mac_address(network['MACAddress'])
            na,c = models.network_adaptor.objects.get_or_create(
                    mac_address=mac_address,
                    defaults={'seen_first': data_datetime, 'seen_last': data_datetime},
            )

            # Ensure same hardware not installed on same computer multiple times
            if na.pk is not None and na.pk in seen_hardware:
                raise import_error("We have already seen this network adaptor '%s' on this computer"%(na.pk))
            else:
                seen_hardware[na.pk] = True

            # sanity check
            if na.installed_on is not None and na.installed_on.pk != computer.pk:
                raise import_error("The network adaptor '%s' (%d) is installed on another computer"%(na,na.pk))

            na.installed_on = computer
            na.name         = son(network['Name'])
            na.network_type = son(network['AdapterType'])
            # FIXME
            # na.IPv4_address = son(network['NetworkAdapterConfig'][0]['IPAddress'])
            na.seen_last    = data_datetime
            na.auto_delete  = True

            # Update manufacturer, if required
            value = son(network['Manufacturer'])
            if c or has_changed(na.auto_manufacturer,na.manufacturer,value):
                na.manufacturer = value
            na.auto_manufacturer = value

            # Save values
            na.save()

            if na.pk in hardware:
                hardware.remove(na.pk)

    for disk_drive in data_dict['DiskDrive']:
            if disk_drive['Manufacturer'] == "":
                raise import_error("No manufacturer given for DiskDrive")

            serial_number = None
            if "SerialNumber" in disk_drive:
                serial_number = son(disk_drive['SerialNumber'])

            c = False
            s = None
            # First try, ideal match
            if s is None and serial_number is not None:
                try:
                    s = models.storage.objects.get(
                            auto_manufacturer=disk_drive['Manufacturer'],
                            auto_model=disk_drive['Model'],
                            auto_serial_number=serial_number,
                            total_size=son(disk_drive['TotalSectors']),
                            sector_size=son(disk_drive['BytesPerSector']),
                    )
                except models.storage.DoesNotExist, e:
                    pass

            # Second try, we weren't given a serial number. Cannot uniquely
            # identify disk.  Guess work required.
            if s is None and serial_number is None:
                try:
                    s = models.storage.objects.get(
                            installed_on=computer,
                            used_by=computer,
                            auto_manufacturer=disk_drive['Manufacturer'],
                            auto_model=disk_drive['Model'],
                            total_size=son(disk_drive['TotalSectors']),
                            sector_size=son(disk_drive['BytesPerSector']),
                    )
                except models.storage.DoesNotExist, e:
                    pass

            # Third try, if there is only one storage device on this
            # computer and it has empty values, go for it
            if s is None:
                try:
                    s = models.storage.objects.get(
                            installed_on=computer,
                            used_by=computer,
                            total_size__isnull=True,
                            sector_size__isnull=True,
                            auto_manufacturer__isnull=True,
                            auto_model__isnull=True,
                            auto_serial_number__isnull=True,
                    )
                except models.storage.DoesNotExist, e:
                    pass

            # Forth try, just create a new one
            if s is None:
                s = models.storage()
                c = True
                s.seen_first=data_datetime

            # Ensure same hardware not installed on same computer multiple times
            if s.pk is not None and s.pk in seen_hardware:
                raise import_error("We have already seen this storage '%s' on this computer"%(s.pk))
            else:
                seen_hardware[s.pk] = True

            # sanity checks
            if s.installed_on is not None and s.installed_on.pk != computer.pk:
                raise import_error("The storage device '%s' (%d) is installed on another computer"%(s,s.pk))

            if s.used_by is not None and s.used_by.pk != computer.pk:
                raise import_error("The storage device '%s' (%d) is in use by another computer"%(s,s.pk))

            # Update values
            s.serial_number= serial_number
            s.total_size   = son(disk_drive['TotalSectors'])
            s.sector_size  = son(disk_drive['BytesPerSector'])
            s.seen_last    = data_datetime
            s.auto_delete  = True
            s.installed_on = computer
            s.used_by      = computer

            # Update manufacturer, if required
            value = son(disk_drive['Manufacturer'])
            if c or has_changed(s.auto_manufacturer,s.manufacturer,value):
                s.manufacturer = value
            s.auto_manufacturer = value

            # Update model, if required
            value = son(disk_drive['Model'])
            if c or has_changed(s.auto_model,s.model,value):
                s.model = value
            s.auto_model = value

            # Save values
            s.save()

            if s.pk in hardware:
                hardware.remove(s.pk)

            if s.pk in used_storage:
                used_storage.remove(s.pk)

    # delete old hardware
    models.hardware.objects.filter(pk__in=hardware,auto_delete=True).update(installed_on=None)
    models.storage.objects.filter(pk__in=used_storage,auto_delete=True).update(used_by=None)

def get_license_keys(data_dict):
    license_keys = {}
    for license_key in data_dict['license key']:
        name = license_key['Name']
        key = license_key['Product Key']
        if key not in license_keys:
            license_keys[name] = key
        elif license_keys[name] != key:
            print "Warning: found different key for software '%s'"%(name)

    return license_keys

def install_software(data_datetime, os, name, version, license_keys):
    key = hacks.get_license_key(name, license_keys)

    list = hacks.strip_software_version(name)
    for new_name, new_version in list:
        try:
            software = models.software.objects.get(name=new_name)
        except models.software.DoesNotExist, e:
            print "Creating software '%s'"%(new_name)
            software = models.software.objects.create(name=new_name)

        try:
            c = False
            si = models.software_installation.objects.get(
                    os = os,
                    software = software,
                    active = True,
            )
        except models.software_installation.DoesNotExist, e:
            c = True
            si = models.software_installation()
            si.os = os
            si.software = software
            si.active = True
            si.seen_first = data_datetime
            si.seen_last = data_datetime

        if c:
            print u"Installing '%s' version '%s'"%(name, version)
            print u"... simplified as '%s' version '%s'" % (new_name, version)
            print u"... os '%s' storage '%s'"%(os, os.storage)

        si.software_version = version
        si.auto_delete = True
        si.seen_last = data_datetime

        # Where we given a license key?
        if c or has_changed(si.auto_license_key,si.license_key,key):
            print "Updating license key of '%s' from '%s' to '%s'"%(new_name,si.license_key,key)
            if key is not None:
                try:
                    si.license_key = models.license_key.objects.get(
                            software=software,
                            key=key,
                    )
                except models.license_key.DoesNotExist, e:
                    raise import_error("Cannot find license key '%s' for software '%s'"%(key,software))
            else:
                si.license_key = None

        # Update the last seen key with what we just got
        si.auto_license_key = key

        # Save install and return
        si.save()
        return si

def sync_software(data_datetime, os, data_dict):
    os.name               = son(data_dict['OperatingSystem'][0]['Caption'])
    os.computer_name      = son(data_dict['OperatingSystem'][0]['CSName'])
    os.seen_last          = data_datetime

    si_list = [ si.pk for si in os.active_software_installations() ]

    license_keys = get_license_keys(data_dict)

    software_list = {}
    for product in data_dict['Product']:
        if product['Name'] == "":
            name = "null"
        else:
            name = product['Name']

        version = son(product['Version'])
        si = install_software(data_datetime, os, name, version, license_keys)
        if si.pk in si_list:
            si_list.remove(si.pk)

    # operating system does not appear in in software list, however we should add it if
    # we detect the license key
    for product in data_dict['OperatingSystem']:
        name = product['Caption']
        version = u"%s SP%s.%s"%(
                product['Version'],
                product['ServicePackMajorVersion'],
                product['ServicePackMinorVersion'],
        )
        si = install_software(data_datetime, os, name, version, license_keys)
        if si.pk in si_list:
            si_list.remove(si.pk)

    # delete old software
    models.software_installation.objects.filter(pk__in=si_list, auto_delete=True).update(active=False)

def get_datetime(data_dict):
    (year,month,day) = data_dict['Lintory'][0]['Date'].split("-")
    (hour,minute,second) = data_dict['Lintory'][0]['Time'].split(":")
    return datetime.datetime(
            year=int(year),
            month=int(month),
            day=int(day),
            hour=int(hour),
            minute=int(minute),
            second=int(second),
    )

def load(data):
    # Should never happen, but check just to be sane
    if data.format != "windows":
        raise RuntimeError("We only support windows format here")

    # parse all the data into a python dictionary
    data_dict = parse_file(data.file)

    try:
        data.errors = ""

        # HARDWARE

        if data.computer is None:
            try:
                data.computer = get_computer(data_dict)
                print "computer %s (%d)"%(data.computer,data.computer.pk)
            except computer_does_not_exist, e:
                if data.create_computer:
                    data.computer = create_computer(data.datetime)
                    print "creating computer"
                else:
                    raise


        # Check data is recent
        if data.datetime < data.computer.seen_last:
            data.errors += u"Warning: Computer data is older than last update\n"
        else:
            sync_hardware(data.datetime, data.computer, data_dict)

        data.computer.save()

        # SOFTWARE

        if data.os is None:
            try:
                data.os = get_os(data.computer, data_dict)
                print "os %s (%d)"%(data.os,data.os.pk)
            except os_does_not_exist, e:
                if data.create_os:
                    data.os = create_os(data.datetime, data.computer, data_dict)
                    print "creating os"
                else:
                    raise

        print "os is on storage %s (%d)"%(data.os.storage,data.os.storage.pk)

        # Check data is recent
        if data.datetime < data.os.seen_last:
            data.errors += "Warning: OS data is older than last update\n"
        else:
            # Check the OS storage is used by this computer
            if data.os.storage.used_by is not None:
                if data.os.storage.used_by.pk != data.computer.pk:
                    raise import_error("OS storage is in use on another computer")
            else:
                raise import_error("OS storage is not marked in use on any computer")

            sync_software(data.datetime, data.os, data_dict)

        if data.errors == "":
            data.errors = None

        data.imported = datetime.datetime.now()
        data.os.save()

    except import_error, e:
        # Ooops. Something went wrong. Sob.
        data.errors += u"The following error occured during importing:\n%s"%(e.value)

    # SAVE RECORD
    data.last_attempt = datetime.datetime.now()
    data.save()
