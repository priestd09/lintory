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

from django.forms.util import ValidationError
from django import forms

import lintory.models as models
import re

class object_name_field(forms.CharField):

    def __init__(self, object, queryset=None, to_field_name=None, *args, **kwargs):
        self.object = object
        super(object_name_field, self).__init__(*args, **kwargs)

    def clean(self, value):
        value=super(object_name_field, self).clean(value)

        if value in ('',None):
            return None

        try:
            clean=self.object.objects.get(name=value)
        except self.object.DoesNotExist, e:
            raise ValidationError(u"Cannot find object %s: %s" % (value,e))

        return clean

class char_field(forms.CharField):

    def clean(self, value):
        super(char_field, self).clean(value)

        if value in ('',None):
            return None
        return value

class email_field(forms.EmailField):

    def clean(self, value):
        super(email_field, self).clean(value)

        if value in ('',None):
            return None
        return value

class computer_field(object_name_field):

    def __init__(self, *args, **kwargs):
        super(computer_field, self).__init__(models.computer, *args, **kwargs)


class software_field(object_name_field):

    def __init__(self, *args, **kwargs):
        super(software_field, self).__init__(models.software, *args, **kwargs)


class location_field(object_name_field):
    def __init__(self, *args, **kwargs):
        super(location_field, self).__init__(models.location, *args, **kwargs)


class license_field(forms.IntegerField):
    def clean(self, value):
        value=super(license_field, self).clean(value)

        if value in ('',None):
            return None

        try:
            license=models.license.objects.get(id=value)
        except models.license.DoesNotExist, e:
            raise ValidationError(u"Cannot find license %s: %s" % (value,e))

        return value

class mac_address_field(forms.CharField):
    def clean(self, value):
        value=super(mac_address_field, self).clean(value)

        if value in ('',None):
            return None

        value = value.upper()

        g = u"[A-F0-9][A-F0-9]";
        m = re.match(u"^(%s)-(%s)-(%s)-(%s)-(%s)-(%s)$"
                     %(g,g,g,g,g,g),value)
        if m != None:
                value = "%s:%s:%s:%s:%s:%s"%(m.group(1),m.group(2),m.group(3),m.group(4),m.group(5),m.group(6))

        m = re.match(u"^(%s):(%s):(%s):(%s):(%s):(%s)$"
                     %(g,g,g,g,g,g),value)
        if m == None:
            raise ValidationError(u"Unrecognised MAC address %s" % (value))

        return value
