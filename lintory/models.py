# lintory - keep track of computers and licenses
# Copyright (C) 2008-2009 Brian May
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core.files.storage import FileSystemStorage
from django.core.urlresolvers import reverse
from django.utils.encoding import smart_unicode
from django.db import models
from django.template import loader

import lintory.mfields as fields

from datetime import *
import random
import re

# BASE ABSTRACT MODEL CLASS

class base_model(models.Model):

    class Meta:
        abstract = True

    def get_history(self):
        ct = ContentType.objects.get_for_model(self)
        return history_item.objects.filter(content_type=ct, object_pk=self.pk)

    def error_list(self):
        error_list = []
        return error_list

    # are there any reasons why this object should not be deleted?
    def check_delete(self):
        error_list = []
        return error_list

#########
# PARTY #
#########

class party(base_model):
    name     = fields.char_field(max_length=30)
    LDAP_DN  = fields.char_field(max_length=104, null=True, blank=True, db_index=True)
    comments = fields.text_field(null=True, blank=True)

    def owns_software(self):
        return software.objects.filter(license_key__license__owner = self).distinct()

    def __unicode__(self):
        return self.name

    # are there any reasons why this object should not be deleted?
    def check_delete(self):
        error_list = []
        if self.assigned_hardware_tasks.all().count() > 0:
            errorlist.append("Cannot delete party that is assigned a task")
        if self.owns_locations.all().count() > 0:
            errorlist.append("Cannot delete party that owns locations")
        if self.uses_locations.all().count() > 0:
            errorlist.append("Cannot delete party that uses locations")
        if self.owns_licenses.all().count() > 0:
            errorlist.append("Cannot delete party that owns licenses")
        if self.owns_hardware.all().count() > 0:
            errorlist.append("Cannot delete party that owns hardware")
        if self.uses_hardware.all().count() > 0:
            errorlist.append("Cannot delete party that uses hardware")
        return error_list

class Nobody:

    def __unicode__(self):
        return "Nobody"

    def __init__(self):
        self.pk = "none"
        self.LDAP_DN = None
        self.assigned_hardware_tasks = hardware_task.objects.filter(assigned__isnull=True,
                date_complete__isnull=True)
        self.owns_locations = location.objects.filter(owner__isnull=True)
        self.uses_locations = location.objects.filter(user__isnull=True)
        self.owns_licenses = license.objects.filter(owner__isnull=True)
        self.owns_hardware = hardware.objects.filter(owner__isnull=True,
                date_of_disposal__isnull=True)
        self.uses_hardware = hardware.objects.filter(user__isnull=True,
                date_of_disposal__isnull=True)
        self.owns_software = software.objects.filter(
                license_key__isnull = False,
                license_key__license__owner__isnull = True).distinct()

    def error_list(self):
        error_list = []
        return error_list

    # are there any reasons why this object should not be deleted?
    def check_delete(self):
        error_list = []
        error_list.append("Cannot delete nobody as nobody is somebody")
        return error_list

###########
# HISTORY #
###########

class history_item(base_model):
    # Content-object field
    content_type   = models.ForeignKey(ContentType,
            related_name="content_type_set_for_%(class)s")
    object_pk      = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey(ct_field="content_type", fk_field="object_pk")

    date  = models.DateTimeField()
    title = fields.char_field(max_length=80)
    body  = fields.text_field(null=True,blank=True)

    def __unicode__(self):
        return u"history item %s"%(self.title)

##########
# VENDOR #
##########

class vendor(base_model):
    name     = fields.char_field(max_length=30)
    url      = models.URLField(null=True,blank=True)
    address  = fields.text_field(null=True, blank=True)
    telephone = fields.char_field(max_length=20, null=True, blank=True)
    email    = fields.email_field(null=True, blank=True)
    comments = fields.text_field(null=True, blank=True)

    def __unicode__(self):
        return self.name

    def check_delete(self):
        errorlist = []

        if self.software_set.all().count() > 0:
            errorlist.append("Cannot delete vendor with software")
        if self.hardware_set.all().count() > 0:
            errorlist.append("Cannot delete vendor with hardware")
        if self.license_set.all().count() > 0:
            errorlist.append("Cannot delete vendor with licenses")
        if self.computer_set.all().count() > 0:
            errorlist.append("Cannot delete vendor with computers")

        return errorlist

############
# LOCATION #
############

class location(base_model):
    name    = fields.char_field(max_length=30)
    address = fields.text_field(null=True,blank=True)
    owner   = models.ForeignKey(party,null=True,blank=True, related_name='owns_locations')
    user    = models.ForeignKey(party,null=True,blank=True, related_name='uses_locations')
    parent  = models.ForeignKey('self',related_name='children',null=True,blank=True)

    comments = fields.text_field(null=True,blank=True)

    def __unicode__(self):
        return self.name

    def _get_self_or_children(self, seen):
        if self.pk in seen:
            return []

        seen[self.pk] = True
        list = [ self ]
        children = location.objects.filter(parent=self)
        for child in children:
                list.extend(child._get_self_or_children(seen))

        return list

    def get_self_or_children(self):
        seen = {}
        return self._get_self_or_children(seen)

    def get_hardware(self):
        return self.hardware_set.filter(date_of_disposal__isnull=True);

    def get_self_or_children_hardware(self):
        children = self.get_self_or_children();
        return hardware.objects.filter(location__in=children,date_of_disposal__isnull=True);

    def get_owner(self):
        return self.owner

    def get_user(self):
        return self.user

    class Meta:
        ordering = ('name',)

    def check_delete(self):
        errorlist = []
        return errorlist

    def tasks(self):
        hardware = self.get_self_or_children_hardware()
        return task.objects.filter(hardware_task__hardware__in=hardware,hardware_task__date_complete__isnull=True).distinct()

    def error_list(self):
        error_list = super(location,self).error_list()

        if self.owner is None:
            error_list.append("Owner not defined")

        return error_list

############
# HARDWARE #
############

hardware_types = {
    'motherboard': True,
    'processor': True,
    'video_controller': True,
    'network_adaptor': True,
    'storage': True,
    'power_supply': True,
    'computer': True,
    'monitor':True,
    'multifunction': True,
    'printer': True,
    'scanner': True,
    'docking_station': True,
    'camera': True,
}

HARDWARE_CHOICES = [ (t, t.replace("_", " ")) for t in hardware_types ]

class hardware(base_model):
    type_id       = fields.char_field(max_length=20, choices=HARDWARE_CHOICES)
    seen_first    = models.DateTimeField()
    seen_last     = models.DateTimeField()
    manufacturer  = fields.char_field(max_length=50,null=True,blank=True)
    model         = fields.char_field(max_length=90,null=True,blank=True)
    product_number= fields.char_field(max_length=30,null=True,blank=True)
    serial_number = fields.char_field(max_length=50,null=True,blank=True)
    service_number= fields.char_field(max_length=10,null=True,blank=True)
    date_of_manufacture = models.DateTimeField(null=True,blank=True)
    date_of_disposal    = models.DateTimeField(null=True,blank=True)
    asset_id = fields.char_field(max_length=10,null=True,blank=True)
    owner   = models.ForeignKey(party,null=True,blank=True, related_name='owns_hardware')
    user    = models.ForeignKey(party,null=True,blank=True, related_name='uses_hardware')
    location = models.ForeignKey(location,null=True,blank=True)
    vendor  = models.ForeignKey(vendor,null=True,blank=True)

    installed_on  = models.ForeignKey('self',related_name='installed_hardware',null=True,blank=True)
    auto_delete = models.BooleanField()
    auto_manufacturer = fields.char_field(max_length=50,null=True,blank=True,db_index=True)
    auto_model = fields.char_field(max_length=90,null=True,blank=True,db_index=True)
    auto_serial_number = fields.char_field(max_length=50,null=True,blank=True,db_index=True)

    comments = fields.text_field(null=True,blank=True)

    def __unicode__(self):
        return "%s - %s %s"%(self.type_id,self.manufacturer,self.model)

    class Meta:
        ordering = ('type_id', 'manufacturer','model')

    def get_owner(self):
        return self.owner

    def get_user(self):
        return self.user

    # get the object type_id of this hardware item
    def get_object_type_id(self):
        if self.type_id is not None and self.type_id!="":
            type_id = self.type_id
        elif type(self) != hardware:
            type_id = type(self).__name__
        else:
            raise RuntimeError("Unknown type for generic hardware type")

        return type_id

    # get the object for this hardware item
    def get_object(self):
        # No need to get type data if we we already that type
        type_id = self.get_object_type_id()
        if type(self).__name__ == type_id:
            return self

        if type_id in hardware_types:
            return getattr(self,type_id)
        else:
            raise RuntimeError("Unknown hardware type %s"%(self.type))

    def hardware_tasks_all(self):
        return self.hardware_task_set.all()

    def hardware_tasks_done(self):
        return self.hardware_task_set.filter(date_complete__isnull=False)

    def hardware_tasks_todo(self):
        return self.hardware_task_set.filter(date_complete__isnull=True)

    def check_delete(self):
        errorlist = []
        if self.installed_on != None:
            errorlist.append("Cannot delete hardware that is installed")
        return errorlist

    def network_adaptors(self):
        return network_adaptor.objects.filter(installed_on=self)

    def _update_installed_hardware(self, user, owner, location, seen):
        if self.pk in seen:
            return []

        seen[self.pk] = True

        installed_hardware = hardware.objects.filter(installed_on=self)
        installed_hardware.update(user=user, owner=owner, location=location)

        for child in installed_hardware:
            child._update_installed_hardware(user, owner, location, seen)

    def update_installed_hardware(self, user, owner, location):
        seen = {}
        self._update_installed_hardware(user, owner, location, seen)

    # We need to make sure that type_id is set before saving
    def save(self, *args,**kwargs):
        self.type_id = self.get_object_type_id()

        if self.installed_on is not None:
            user = self.installed_on.user
            owner = self.installed_on.owner
            location = self.installed_on.location
            self.user = user
            self.owner = owner
            self.location = location
        else:
            user = self.user
            owner = self.owner
            location = self.location

        super(hardware,self).save(*args, **kwargs)
        self.update_installed_hardware(user=user, owner=owner, location=location)

    save.alters_data = True

    def error_list(self):
        error_list = super(hardware,self).error_list()
        if self.installed_on is not None:
            if self.location != self.installed_on.location:
                error_list.append("Location different to installed hardware location")
            if self.owner != self.installed_on.owner:
                error_list.append("Owner different to installed hardware owner")
            if self.user != self.installed_on.user:
                error_list.append("User different to installed hardware user")
            if self.date_of_disposal != self.installed_on.date_of_disposal:
                error_list.append("Date of disposal different to installed date of disposal user")
        else:
            if self.location is None:
                error_list.append("Location not defined")
            if self.owner is None:
                error_list.append("Owner not defined")
            # We don't care if user is not defined

        return error_list

class motherboard(hardware):
    type = fields.char_field(max_length=20)

    def __unicode__(self):
        return "'%s' compatable motherboard"%(self.type)

class processor(hardware):
    number_of_cores = models.PositiveIntegerField()
    cur_speed = models.PositiveIntegerField()
    max_speed = models.PositiveIntegerField()
    version   = fields.char_field(max_length=40,null=True,blank=True)

    def __unicode__(self):
        return "%d MHz processor"%(self.max_speed)

class video_controller(hardware):
    memory = models.DecimalField(max_digits=12,decimal_places=0,null=True,blank=True)

    def __unicode__(self):
        return "%s video controller"%(self.manufacturer)

NETWORK_TYPE = (
    ('Ethernet 802.3', 'Ethernet 802.3'),
)

class network_adaptor(hardware):
    name = fields.char_field(max_length=100)
    network_type = models.CharField(max_length=20, choices=NETWORK_TYPE)
    mac_address = fields.mac_address_field(db_index=True)

    def inet6_host_id(self):
        mac = self.mac_address.split(':')
        mac[3:3] = ['ff', 'fe']
        mac = [ int(i,16) for i in mac ]
        mac[0] = mac[0] | 2

        addr = []
        for i in range(0,4):
                addr.append(mac[i*2] << 8 | mac[i*2+1])

        return u"%x:%x:%x:%x"%(addr[0],addr[1],addr[2],addr[3])

    def __unicode__(self):
        return "%s network adaptor"%(self.manufacturer)

    def error_list(self):
        error_list = super(network_adaptor,self).error_list()

        g = u"[A-F0-9][A-F0-9]";
        m = re.match(u"^(%s):(%s):(%s):(%s):(%s):(%s)$"
                     %(g,g,g,g,g,g),self.mac_address)
        if m is None:
            error_list.append(u"Mac address %s not in required format"%(self.mac_address))

        duplicates = network_adaptor.objects.filter(mac_address=self.mac_address).exclude(pk=self.pk)
        if duplicates.count() > 0:
            error_list.append(u"Ethernet address %s is duplicated"%(self.mac_address))

        return error_list

class storage(hardware):
    used_by  = models.ForeignKey('computer',related_name='used_storage',null=True,blank=True)
    total_size = models.DecimalField(max_digits=12,decimal_places=0,null=True,blank=True)
    sector_size = models.PositiveIntegerField(null=True,blank=True)
    signature = fields.char_field(max_length=12,db_index=True,null=True,blank=True)

    def os_list(self):
        return self.os_set.all()

    def active_software_installations(self):
        os_list = self.os_list()
        return software_installation.objects.filter(active=True, os__in=os_list)

    def inactive_software_installations(self):
        os_list = self.os_list()
        return software_installation.objects.filter(active=False, os__in=os_list)

    def check_delete(self):
        errorlist = super(storage,self).check_delete()
        if self.installed_on != None:
            errorlist.append("Cannot delete storage that is in use on a computer")
        if self.os_set.all().count() > 0:
            errorlist.append("Cannot delete storage with OS")
        return errorlist

    def memory(self):
        if self.total_size is not None:
            if self.sector_size is not None:
                return self.total_size*self.sector_size

    def __unicode__(self):
        size = self.memory()
        if size is None:
            return u"harddisk"

        units = "bytes"

        if size > 1000:
            size = size / 1000
            units = "KB"

        if size > 1000:
            size = size / 1000
            units = "MB"

        if size > 1000:
            size = size / 1000
            units = "GB"

        if size > 1000:
            size = size / 1000
            units = "TB"

        return u"%d %s harddisk"%(size, units)

    def error_list(self):
        error_list = super(storage,self).error_list()
        if self.installed_on is not None:
            if self.used_by is None:
                error_list.append("Storage is installed but not marked in use")
            elif self.installed_on.pk != self.used_by.pk:
                # Not an error really, but just in case
                error_list.append("Storage is installed but in use by different machine")
        return error_list

class power_supply(hardware):
    is_portable = models.BooleanField()
    watts = models.PositiveIntegerField()

    def __unicode__(self):
        return "%d watts power supply"%(self.watts)

class computer(hardware):
    name = fields.char_field(max_length=20)
    is_portable = models.BooleanField()

    memory = models.DecimalField(max_digits=12,decimal_places=0,null=True,blank=True)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ('name','asset_id')

    def seen_first_delta(self):
        return datetime.now() - self.seen_first

    def seen_last_delta(self):
        return datetime.now() - self.seen_last

    def os_list(self):
        storage_list = self.used_storage.all()
        return os.objects.filter(storage__in=storage_list)

    def active_software_installations(self):
        os_list = self.os_list()
        return software_installation.objects.filter(active=True, os__in=os_list)

    def inactive_software_installations(self):
        os_list = self.os_list()
        return software_installation.objects.filter(active=False, os__in=os_list)

    def check_delete(self):
        errorlist = super(computer,self).check_delete()
        if self.license_set.all().count() > 0:
            errorlist.append("Cannot delete computer with licenses")
        if self.installed_hardware.all().count() > 0:
            errorlist.append("Cannot delete computer with installed hardware")
        if self.used_storage.all().count() > 0:
            errorlist.append("Cannot delete computer with used storage")
        return errorlist

MONITOR_TECHNOLOGY = (
    ('CRT', 'Cathode Ray Tube'),
    ('LCD', 'Liquid Crystal Display'),
    ('Plasma', 'Plasma'),
)

class monitor(hardware):
    size = models.FloatField(null=True,blank=True)
    width = models.PositiveIntegerField(null=True,blank=True)
    height = models.PositiveIntegerField(null=True,blank=True)
    widescreen = models.BooleanField()
    technology = models.CharField(max_length=10, choices=MONITOR_TECHNOLOGY)

    def __unicode__(self):
        text = ""
        if self.size is not None:
            text += u"%s\" "%(self.size)

        if self.widescreen:
            text += u"widescreen "

        if self.technology:
            text += u"%s "%(self.technology)

        text += u"monitor"
        return text

class multifunction(hardware):
    can_send_fax = models.BooleanField()
    can_receive_fax = models.BooleanField()

    accessible_on_network = models.BooleanField()
    admin_url = models.URLField(null=True,blank=True)
    user_url = models.URLField(null=True,blank=True)
    windows_path = fields.char_field(max_length=100,null=True,blank=True)

    def __unicode__(self):
        return "%s %s"%(self.manufacturer,self.model)

PRINTER_TECHNOLOGY = (
    ('Inkjet', 'Inkjet'),
    ('Laser', 'Laser'),
    ('LED', 'LED'),
)
class printer(hardware):
    technology = models.CharField(max_length=10, choices=PRINTER_TECHNOLOGY)
    colour = models.BooleanField()
    double_sided = models.BooleanField()
    supports_Postscript = models.BooleanField()
    supports_PCL = models.BooleanField()

    accessible_on_network = models.BooleanField()
    admin_url = models.URLField(null=True,blank=True)
    cups_url = models.URLField(null=True,blank=True)
    windows_path = fields.char_field(max_length=100,null=True,blank=True)

    def __unicode__(self):
        return "%s %s printer"%(self.manufacturer,self.model)

class scanner(hardware):
    colour = models.BooleanField()
    OCR = models.BooleanField()
    auto_feeder = models.BooleanField()
    supports_paper = models.BooleanField()
    supports_tranparencies = models.BooleanField()
    supports_film = models.BooleanField()

    accessible_on_network = models.BooleanField()
    admin_url = models.URLField(null=True,blank=True)
    user_url = models.URLField(null=True,blank=True)
    windows_path = fields.char_field(max_length=100,null=True,blank=True)

    def __unicode__(self):
        return "%s %s scanner"%(self.manufacturer,self.model)

class docking_station(hardware):
    ports = fields.text_field(null=True,blank=True)

    def __unicode__(self):
        return "%s %s docking station"%(self.manufacturer,self.model)

CAMERA_TECHNOLOGY = (
    ('webcam', 'webcam'),
    ('video', 'video'),
    ('film', 'film'),
    ('digital', 'digital'),
    ('SLR', 'SLR'),
    ('DSLR', 'DSLR'),
)
class camera(hardware):
    technology = models.CharField(max_length=10, choices=CAMERA_TECHNOLOGY)
    colour = models.BooleanField()

    takes_stills = models.BooleanField()
    still_x_pixels = models.PositiveIntegerField(null=True,blank=True)
    still_y_pixels = models.PositiveIntegerField(null=True,blank=True)

    takes_videos = models.BooleanField()
    video_x_pixels = models.PositiveIntegerField(null=True,blank=True)
    video_y_pixels = models.PositiveIntegerField(null=True,blank=True)

    def __unicode__(self):
        return "%s %s camera"%(self.manufacturer,self.model)

######
# OS #
######

class os(base_model):
    storage = models.ForeignKey(storage)
    name = fields.char_field(max_length=40, db_index=True)
    computer_name = fields.char_field(max_length=20, db_index=True)
    seen_first    = models.DateTimeField()
    seen_last     = models.DateTimeField()

    comments = fields.text_field(null=True,blank=True)

    def __unicode__(self):
        name = self.name
        name = name.replace("Microsoft ","")
        name = name.replace(" Home","")
        name = name.replace(" Premium","")
        name = name.replace(" Professional","")
        name = name.replace(" (R)","")
        name = name.replace(" Standard","")
        name = name.replace(" (TM)","")
        name = name.replace(" Ultimate","")
        return "%s (%s)"%(self.computer_name,name)

    class Meta:
        ordering = ('storage', 'name')

    def seen_first_delta(self):
        return datetime.now() - self.seen_first

    def seen_last_delta(self):
        return datetime.now() - self.seen_last

    def active_software_installations(self):
        return self.software_installation_set.filter(active=True)

    def inactive_software_installations(self):
        return self.software_installation_set.filter(active=False)

    def check_delete(self):
        errorlist = []
        return errorlist

############
# SOFTWARE #
############
class software(base_model):
    name = fields.char_field(max_length=100)
    comments = fields.text_field(null=True,blank=True)
    vendor  = models.ForeignKey(vendor,null=True,blank=True)

    def __unicode__(self):
        return self.name

    class Meta:
        ordering = ('name',)

    def licenses(self):
        return license.objects.filter(license_key__software=self).distinct()

    def software_installations_max(self):
        software_installations_max = None
        for l in self.licenses():
            m = l.installations_max
            if m is not None:
                if software_installations_max is None:
                    software_installations_max = m
                else:
                    software_installations_max += m
            else:
                return None
        return software_installations_max

    def software_installations_found(self):
        list = self.active_software_installations()
        return list.count()

    def software_installations_left(self):
        max = self.software_installations_max()
        if max is not None:
                return max - self.software_installations_found()
        else:
                return None

    def active_software_installations(self):
        return software_installation.objects.filter(software=self,active=True)

    def inactive_software_installations(self):
        return software_installation.objects.filter(software=self,active=False)

    def check_delete(self):
        errorlist = []
        if self.license_key_set.all().count() > 0:
            errorlist.append("Cannot delete software with license keys")
        if self.active_software_installations().count() > 0:
            errorlist.append("Cannot delete software with active installations")
        return errorlist

###########
# LICENSE #
###########

class license(base_model):
    name = fields.char_field(max_length=100,null=True,blank=True,db_index=True)
    vendor  = models.ForeignKey(vendor,null=True,blank=True)
    vendor_tag = fields.char_field(max_length=10,null=True,blank=True)
    installations_max = models.PositiveIntegerField(null=True,blank=True)
    version    = fields.char_field(max_length=20,null=True,blank=True)
    computer = models.ForeignKey(computer,null=True,blank=True)
    expires = models.DateTimeField(null=True,blank=True)
    owner   = models.ForeignKey(party,null=True,blank=True, related_name='owns_licenses')
    text = fields.text_field(null=True,blank=True)
    comments = fields.text_field(null=True,blank=True)

    def __unicode__(self):
        if self.name is not None:
            name = self.name
        else:
            name = u"L%s"%(self.id)

        if self.vendor_tag is not None:
            name +=u" (%s)"%(self.vendor_tag)

        return name

    def software_installations_found(self):
        list = self.active_software_installations()
        return list.count()

    def software_installations_left(self):
        max=self.installations_max
        if max is None:
            return None
        else:
            return max - self.software_installations_found()

    def active_software_installations(self):
        return software_installation.objects.filter(active=True,license_key__license=self)

    def inactive_software_installations(self):
        return software_installation.objects.filter(active=False,license_key__license=self)

    def get_owner(self):
        return self.owner

    def error_list(self):
        error_list = super(license,self).error_list()

        if self.name is not None:
            duplicates = license.objects.filter(name=self.name).exclude(pk=self.pk)
            if duplicates.count() > 0:
                error_list.append(u"License name %s is duplicated"%(self.name))

        if self.owner is None:
            error_list.append("No owner defined")

        if self.license_key_set.count() == 0:
            error_list.append(u"no license keys defined for license")

        left = self.software_installations_left()
        if left is not None and left < 0:
            error_list.append(u"Negative installations left")

        for lk in self.license_key_set.all():
            error_list.extend(lk.error_list())

        return error_list

    def check_delete(self):
        errorlist = []
        if self.software_installations_found() > 0:
            errorlist.append("Cannot delete license with installations")
        return errorlist

###############
# LICENSE KEY #
###############

class license_key(base_model):
    software = models.ForeignKey(software)
    license  = models.ForeignKey(license)
    key = fields.char_field(max_length=50,null=True,blank=True,db_index=True)
    comments = fields.text_field(null=True,blank=True)

    class Meta:
        ordering = ('software','license','key')
        permissions = (
            ("can_see_key", "Can see license key"),
        )


    def __unicode__(self):
        return "LK%d"%(self.pk)

    def active_software_installations(self):
        return software_installation.objects.filter(active=True,license_key=self)

    def inactive_software_installations(self):
        return software_installation.objects.filter(active=False,license_key=self)

    def software_installations_found(self):
        list = self.active_software_installations()
        return list.count()

    def error_list(self):
        error_list = super(license_key,self).error_list()

        duplicates = license_key.objects.filter(
                models.Q(software=self.software,key=self.key) |
                models.Q(software=self.license,key=self.key)
                ).exclude(pk=self.pk)
        if duplicates.count() > 0:
            error_list.append(u"License key %s is duplicated"%(self.key))

        return error_list

    def check_delete(self):
        errorlist = []
        if self.software_installations_found() > 0:
            errorlist.append("Cannot delete license key with installations")
        return errorlist

#########################
# SOFTWARE_INSTALLATION #
#########################

class software_installation(base_model):
    os = models.ForeignKey(os)
    software = models.ForeignKey(software)
    active = models.BooleanField()
    seen_first = models.DateTimeField()
    seen_last  = models.DateTimeField()

    license_key = models.ForeignKey(license_key,null=True,blank=True)

    software_version = fields.char_field(max_length=20,null=True,blank=True)

    auto_license_key = fields.char_field(max_length=50,null=True,blank=True)
    auto_delete = models.BooleanField()

    comments = fields.text_field(null=True,blank=True)

    def seen_first_delta(self):
        return datetime.now() - self.seen_first

    def seen_last_delta(self):
        return datetime.now() - self.seen_last

    class Meta:
        ordering = ('os','software','license_key')

    def error_list(self):
        error_list = super(software_installation,self).error_list()

        # Errors don't matter if this installation was deleted!
        if not self.active:
            return error_list

        # Is there a license associated?
        if self.license_key is not None:
            # Yes, we better check it is valid
            if self.software != self.license_key.software:
                error_list.append(u"software %s does not match license key software %s"%(self.software,self.license_key.software))

            license=self.license_key.license;

            # Check the version to see if it is allowed by license
            versions_allowed=license.version
            if versions_allowed is not None and versions_allowed!="":
                if self.software_version is None:
                    test_version = ""
                else:
                    test_version = self.software_version
                if not re.match(versions_allowed,test_version):
                    error_list.append(u"version %s is not allowed by license"%(self.software_version))

            # Is this a OEM license for a specific computer?
            if license.computer is not None:
                computer = self.os.storage.used_by
                if computer is not None:
                    if computer.pk != license.computer.pk:
                        error_list.append(u"installation on %s is not allowed by license"%(computer))

            # Does this license expire?
            if license.expires is not None and license.expires < datetime.now():
                error_list.append(u"license has expired")

        # No license, were we expecting one?
        # Assume license required if at least one license for this software
        elif self.software.license_key_set.count() > 0:
                error_list.append(u"no license key set for software software installation")

        return error_list

    def __unicode__(self):
        return self.software.name+"@"+self.os.name

    def check_delete(subject):
        errorlist = []
        if object.active:
            errorlist.append("Cannot delete active software installation")
        return errorlist

########
# TASK #
########

class task(base_model):
    name = fields.char_field(max_length=40)

    comments = fields.text_field(null=True,blank=True)

    def __unicode__(self):
        return self.name

    def hardware_tasks_all(self):
        return self.hardware_task_set.all()

    def hardware_tasks_done(self):
        return self.hardware_task_set.filter(date_complete__isnull=False)

    def hardware_tasks_todo(self):
        return self.hardware_task_set.filter(date_complete__isnull=True)

    def check_delete(self):
        errorlist = []
        # note: delete object *and* delete any associated hardware_task objects.
        return errorlist

#################
# HARDWARE_TASK #
#################

class hardware_task(base_model):
    task = models.ForeignKey(task)
    hardware = models.ForeignKey(hardware)

    date_complete = models.DateTimeField(null=True,blank=True)
    assigned   = models.ForeignKey(party,null=True,blank=True, related_name='assigned_hardware_tasks')

    comments = fields.text_field(null=True,blank=True)

    def __unicode__(self):
        return "task %s on hardware %s"%(self.task,self.hardware.get_object())

    def get_assigned(self):
        return self.assigned

    def check_delete(self):
        errorlist = []
        return errorlist

########
# DATA #
########

data_fs = FileSystemStorage(location=settings.UPLOAD_DIR)

def data_upload_to(instance, filename):
    dt = instance.datetime
    if dt is None:
        dt = datetime.now()

    name = "%s_%04d.txt"%(
            dt.strftime("%Y/%m/%d/%H_%M_%S"),
            random.randint(0, 9999)
    )
    return name

class data(base_model):
    datetime = models.DateTimeField(db_index=True)
    file = models.FileField(upload_to=data_upload_to,storage=data_fs)
    format = fields.char_field(max_length=10)
    computer = models.ForeignKey(computer,null=True,blank=True)
    create_computer = models.BooleanField()
    os = models.ForeignKey(os,null=True,blank=True)
    create_os = models.BooleanField()
    imported = models.DateTimeField(null=True,blank=True)
    last_attempt = models.DateTimeField(null=True,blank=True)
    errors = fields.text_field(null=True, blank=True)
    comments = fields.text_field(null=True, blank=True)

    class Meta:
        ordering = ('datetime','computer',)
