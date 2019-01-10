#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright © 2ndQuadrant Limited <info@2ndquadrant.com>

import copy
from jinja2 import Undefined
from jinja2.runtime import StrictUndefined
from ansible.errors import AnsibleFilterError

# Based on PR ansible/ansible#11083, this filter takes a container and a subkey
# ('x.y.z', or [x,y,z]) and a default value, and returns container.x.y.z or the
# default value if any of the levels is undefined.

def try_subkey(container, keys, default=None):
    try:
        v = container
        if isinstance(keys, basestring):
            keys = keys.split('.')
        for key in keys:
            if isinstance(v, list) and isinstance(key, int):
                v = v[key]
            else:
                v = v.get(key, default)
        if isinstance(v, StrictUndefined):
            v = default
        return v
    except:
        return default

# Given 'foo', returns '"foo"'. Blindly converts each embedded double quote in
# the string to '\"'. Caveat emptor.

def doublequote(str):
    return '"%s"' % str.replace('"', '\"')

# Given a hostname and hostvars, returns the name of the earliest ancestor that
# doesn't have an upstream defined.

def upstream_root(h, hostvars):
    while h in hostvars and hostvars[h].get('upstream', '') != '':
        h = hostvars[h].get('upstream')
    return h

# Given a list of hostnames and the names of a primary instance and some other
# instance (and a copy of hostvars), returns the name of an instance that has
# «backup: xxx» defined and is descended from the primary. It will prefer the
# first backed-up instance in the same region as "somehost", otherwise return
# the first backed-up instance. Returns None if no instances match.

def instance_with_backup_of(hosts, primary, somehost, hostvars):
    candidates = []

    for h in hosts:
        if hostvars[h].get('backup', '') != '' and \
            upstream_root(h, hostvars) == primary:
            candidates.append(h)

    for backedup in candidates:
        if hostvars[backedup].get('region', 'left') == \
            hostvars[somehost].get('region', 'right'):
            return backedup
    if candidates:
        return candidates[0]

    return None

# Takes a list of volumes and returns a new list where there is only one entry
# per device name (raid_device if defined, else device_name), consisting of the
# device name and any variables defined for it.

def get_device_variables(volumes):
    seen = set()
    results = []
    for v in volumes:
        dev = v.get('raid_device', v.get('device_name'))
        if dev not in seen:
            seen.add(dev)
            vars = v.get('vars', {})
            results.append(dict(device=dev, **vars))
    return results

# Takes a dict and a list of keys and returns a new dict which has none of the
# keys in the list.

def remove_keys(d, keys):
    if not isinstance(d, dict):
        raise AnsibleFilterError("|remove_keys takes a dict as its first argument, got " + repr(d))

    if not isinstance(keys, list):
        raise AnsibleFilterError("|remove_keys takes a list as its second argument, got " + repr(keys))

    d2 = copy.deepcopy(d)
    for k in keys:
        if k in d2:
            del d2[k]

    return d2

# Takes a conninfo string and returns a dict of the settings it represents, or
# if given a key, returns the value if the key is specified, or None.

def parse_conninfo(conninfo, key=None):

    settings = {}
    for str in conninfo.split(' '):
        parts = [x.strip() for x in str.strip().split('=', 1)]

        v = None
        if len(parts) == 2:
            v = parts[1]
            while (v.startswith("'") and v.endswith("'")) or \
                    (v.startswith('"') and v.endswith('"')):
                v = v[1:-1]

        settings[parts[0]] = v

    if key:
        return settings.get(key, None)

    return settings

# Takes the name of an image and returns a string corresponding to
# ansible_distribution values.

def identify_os(name):
    name = name.lower()

    if 'rhel' in name or 'redhat' in name:
        return 'RedHat'
    elif 'debian' in name:
        return 'Debian'
    elif 'ubuntu' in name:
        return 'Ubuntu'

    return 'Unknown'

# Given a hash that maps os names to package lists, the name of an os, and an
# optional version suffix, this function returns a list of packages for the
# given os, with the version suffix applied (if provided).

def packages_for(packages, os, version=None):
    ret = []

    for p in packages.get(os, []):
        if not (version is None or isinstance(version, StrictUndefined)):
            sep = '='
            if os == 'RedHat':
                sep = '-'
            p = '%s%s%s' % (p, sep, version)
        ret.append(p)

    return ret

# Given a hash that maps group names to lists of group members (such as the
# global variable "groups"), a group name, and a list of groups to exclude, this
# function returns the members of the named group that are not members of any of
# the excluded groups. Empty and undefined groups are silently ignored.
#
# For example, groups|members_of('role_a', not_in=['role_b','role_c']) would
# return hosts in the group role_a that were not in either groups role_b or
# role_c (as if there were a group named 'role_a_but_not_b_or_c').

def members_of(groups, group, not_in=[]):
    members = set(groups.get(group, []))
    excluded = set()
    for g in not_in:
        excluded |= set(groups.get(g, []))
    return list(members - excluded)

class FilterModule(object):
    def filters(self):
        return {
            'try_subkey': try_subkey,
            'doublequote': doublequote,
            'upstream_root': upstream_root,
            'instance_with_backup_of': instance_with_backup_of,
            'get_device_variables': get_device_variables,
            'remove_keys': remove_keys,
            'parse_conninfo': parse_conninfo,
            'identify_os': identify_os,
            'packages_for': packages_for,
            'members_of': members_of,
        }
