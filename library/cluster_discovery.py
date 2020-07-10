#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# Copyright © 2ndQuadrant Limited <info@2ndquadrant.com>
#
# This module gathers information about a Postgres instance.
#
# There are many questions we could ask about a Postgres server:
#
# * Is postgres installed? If so, where?
#   (⇒ postgres_bin_dir)
#
# * Do the postgres system user and group exist?
#   (⇒ postgres_user, postgres_group)
#
# * Is the postgres data directory initialised?
#   (⇒ postgres_data_dir)
#
# * Is postgres running? If so, where?
#   (⇒ postgres_host, postgres_port, postgres_version)
#
# * Is this a replica? If so, where is it replicating from? Is it using a
#   replication slot? Is it registered as a replica with repmgr? Is the
#   replication up to date?
#
# * How is the kernel configured? How is postgres configured?
#
# * What is the state of the running system? Is it performing well? Is it
#   performing as it usually does? If not, how has it changed?
#
# The answers to all these questions are useful in different situations, whether
# in TPA or otherwise. The data-collector is written to run on an unknown system
# and discover as much about it as possible, either to establish a baseline, or
# to take a snapshot of the system state during an incident.
#
# The circumstances this module expects to operate in, however, are different.
# It executes in a friendly environment (one that was set up by TPA), and the
# data it gathers about the topology of the cluster are used to decide if any
# remedial actions are required to bring the cluster to its desired state.
#
# As such, we focus on questions about the topology of the cluster and the role
# of this particular instance within the cluster. We assume Postgres is already
# installed and running (thereby assuming answers to the first four questions
# above). We connect to Postgres and execute queries that can be used to find
# out the state of replication and decide if anything needs to be done.
#
# We might need to find—rather that assume—answers to earlier questions if we
# needed to run on systems where Postgres was not set up by TPA. That is not the
# case at present, and we already handle the initial setup (even with custom
# packages, user/group, and data directory location). We are also not interested
# in collecting the answers to longer-term performance monitoring questions (in
# the context of this module). If these circumstances change, expanding the
# scope of the questions we ask may be reasonable.

from __future__ import absolute_import, division, print_function

import os, io, sys, pwd, grp
import traceback

from ansible.module_utils.basic import *
from ansible.module_utils.database import *

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2_found = False
else:
    psycopg2_found = True

DOCUMENTATION = '''
---
module: cluster_discovery
short_description: Discover a Postgres server's place in a cluster
description:
   - Performs a sequence of tests against a Postgres server and returns a dict
     of the results as a fact named cluster_facts.
version_added: "2.4"
options:
  conninfo:
    description:
      - A conninfo string for this instance
    required: false
    default: "''"
notes:
   - This module requires the I(psycopg2) Python library to be installed.
requirements: [ psycopg2 ]
author: "Abhijit Menon-Sen <ams@2ndQuadrant.com>"
'''

EXAMPLES = '''
- name: Collect facts about the Postgres cluster
  cluster_discovery:
    conninfo: dbname=postgres
  become_user: "{{ postgres_user }}"
  become: yes
- debug: msg="the data directory is {{ cluster_facts.postgres_data_dir }}"
'''

def main():
    # We need to connect to Postgres as a superuser. The caller must provide a
    # suitable conninfo string and invoke this module as a user that can use it
    # to connect.

    module = AnsibleModule(
        supports_check_mode = True,
        argument_spec = dict(
            conninfo = dict(default=""),
        )
    )

    if not psycopg2_found:
        module.fail_json(msg="the python psycopg2 module is required")

    register_casts()

    m = dict(changed=False)

    conn = None
    try:
        conn = psycopg2.connect(dsn=module.params['conninfo'])
        m.update({
            'ansible_facts': {
                'cluster_facts': cluster_discovery(module, conn)
            }
        })
    except Exception as e:
        m['error'] = str(e)
        m['exception'] = traceback.format_exc()

    module.exit_json(failed=('error' in m), **m)

def cluster_discovery(module, conn):
    m = dict()
    cur = conn.cursor()

    # First, we discover postgres_version and its variants.

    cur.execute("SELECT version()")
    m['postgres_version_string'] = cur.fetchone()[0]
    m['postgres_version_int'] = conn.server_version
    m['postgres_version'] = major_version(conn.server_version)

    # We collect and return everything in pg_settings, and use that to also
    # fill in postgres_data_dir and postgres_port. (There's no easy way to
    # discover postgres_host, but we wouldn't have been able to connect to
    # Postgres in the first place if we didn't have a pretty good idea of
    # what it was set to.)

    m['pg_settings'] = settings = {}
    cur.execute("SELECT name,setting FROM pg_catalog.pg_settings")
    for s in cur.fetchall():
        settings.update({s[0]: s[1]})

    m['postgres_port'] = int(settings['port'])
    m['postgres_data_dir'] = settings['data_directory']

    # A backend pid leads us to /proc/<pid>/{exe,status}, whence we can find
    # postgres_bin_dir, postgres_user, postgres_group, and postgres_home. We
    # assume that we are either running as root, or have permission to read
    # this because we're running as the same user as postgres.

    cur.execute("SELECT pg_backend_pid()")
    pid = cur.fetchone()[0]
    m['postgres_bin_dir'] = os.path.dirname(os.readlink('/proc/%d/exe' % pid))

    for line in io.open('/proc/%d/status' % pid, 'r'):
        s = line.split()

        if not s:
            continue

        if s[0] == 'Uid:':
            ent = pwd.getpwuid(int(s[1]))
            m['postgres_user'] = ent.pw_name
            m['postgres_home'] = ent.pw_dir

        elif s[0] == 'Gid:':
            ent = grp.getgrgid(int(s[1]))
            m['postgres_group'] = ent.gr_name

    # We're done with the basic system facts, so we move on to querying the
    # server to get an idea of its place in the world^Wcluster.

    cur.execute("SELECT pg_is_in_recovery()")
    if cur.fetchone()[0]:
        m['pg_is_in_recovery'] = True
        m['replica'] = replica_discovery(module, conn, m)

    m.update({
        'pg_stat_replication':
        query_results(conn, "SELECT * from pg_catalog.pg_stat_replication")
    })

    m.update({
        'pg_replication_slots':
        query_results(conn, "SELECT * from pg_catalog.pg_replication_slots")
    })

    repmgr = repmgr_discovery(module, conn, m)
    if repmgr is not None:
        m['repmgr'] = repmgr

    m['role'] = 'primary'
    if 'replica' in m:
        m['role'] = 'replica'

    m.update(database_discovery(module, conn, m))

    return m

def major_version(version_num):
    v = str(int(version_num/10000))
    if 10 > int(version_num)/10000:
        v = '%s.%s' % (v, str(int(version_num/100)%10))

    return v

def replica_discovery(module, conn, m0):
    # On a replica, we need primary_conninfo and primary_slot_name. If we
    # are running on 9.6+, we can query pg_stat_wal_receiver, and fall back
    # to reading from recovery.conf on older versions.

    m = dict()
    cur = conn.cursor()

    m.update({
        'recovery_settings': read_recovery_conf(m0)
    })

    if have_pg_stat_wal_receiver(conn):
        res = query_results(conn, "SELECT * from pg_catalog.pg_stat_wal_receiver")
        if len(res) == 1:
            m.update({
                'pg_stat_wal_receiver': res[0],
                'primary_conninfo': res[0]['conninfo'],
                'primary_slot_name': res[0]['slot_name'],
            })

    for k in ['primary_conninfo', 'primary_slot_name']:
        if k not in m and (k in m['recovery_settings'] or k in m0['pg_settings']):
            m.update({
                k: m['recovery_settings'].get(k, m0['pg_settings'].get(k))
            })

    if 'primary_conninfo' in m:
        m.update({
            'primary_conninfo_parts': parse_conninfo(m['primary_conninfo'])
        })

    return m

def repmgr_discovery(module, conn, m0):
    m = dict()

    repmgr_conf = read_repmgr_conf(m0)
    if repmgr_conf is not None:
        m['repmgr_conf'] = repmgr_conf

    if have_repmgr_db(conn):
        repmgr_conn = psycopg2.connect(module.params['conninfo'] + ' dbname=repmgr')

        repmgr_schema = repmgr_schema_name(repmgr_conn)
        if repmgr_schema is not None:
            m['repmgr_schema'] = repmgr_schema
            m['nodes'] = query_results(
                repmgr_conn, "SELECT * FROM \"%s\".nodes" % repmgr_schema
            )

    return m or None

def database_discovery(module, conn, m0):
    m = dict()
    m['databases'] = dict()
    m['bdr_databases'] = []

    cur = conn.cursor()
    cur.execute("""SELECT datname
        FROM pg_catalog.pg_database WHERE datname NOT IN ('template0', 'bdr_supervisordb')""")

    for row in cur:
        datname = row[0]
        results = dict()

        db_conn = psycopg2.connect(module.params['conninfo'] + ' dbname=%s' % datname)

        bdr = bdr_discovery(module, db_conn, m0)
        if bdr is not None:
            results['bdr'] = bdr
            if bdr['node_group']:
                m['bdr_databases'].append(datname)

        m['databases'].update({
            datname: results,
        })

    return m

def bdr_discovery(module, conn, m0):
    m = dict()

    cur = conn.cursor()
    cur.execute("""SELECT relname
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON (c.relnamespace=n.oid)
        WHERE n.nspname = 'bdr' AND c.relname = 'node'""")

    if cur.rowcount > 0:
        m.update({
            'node': query_results(conn, "SELECT * from bdr.node"),
            'node_group': query_results(conn, "SELECT * from bdr.node_group")
        })

    return m or None

def parse_kv(str):
    parts = [x.strip() for x in str.split('=', 1)]

    v = None
    if len(parts) == 2:
        v = parts[1]
        if v.startswith("'") and v.endswith("'") or \
           v.startswith('"') and v.endswith('"'):
            v = v[1:-1]

    return {parts[0]: v}

def parse_conninfo(conninfo):
    settings = {}
    for str in conninfo.split(' '):
        settings.update(parse_kv(str.strip()))

    return settings

def parse_kv_lines(filename):
    m = dict()

    for line in io.open(filename, 'r'):
        line = line.strip()
        if not (line == '' or line.startswith('#')):
            m.update(parse_kv(line))

    return m

def read_recovery_conf(m0):
    recovery_conf = os.path.join(m0['postgres_data_dir'], 'recovery.conf')
    if os.path.isfile(recovery_conf):
        return parse_kv_lines(recovery_conf)
    return {}

def read_repmgr_conf(m0):
    m = None

    repmgr_conf = os.path.join('/etc/repmgr/%s/repmgr.conf' % m0['postgres_version'])
    try:
        m = parse_kv_lines(repmgr_conf)
    except (IOError, OSError):
        pass

    return m

def have_pg_stat_wal_receiver(conn):
    cur = conn.cursor()
    cur.execute("""SELECT relname
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON (c.relnamespace=n.oid)
        WHERE n.nspname = 'pg_catalog' AND c.relname = 'pg_stat_wal_receiver'""")
    return cur.rowcount > 0

def have_repmgr_db(conn):
    cur = conn.cursor()
    cur.execute("SELECT datname FROM pg_catalog.pg_database WHERE datname='repmgr'")
    return cur.rowcount > 0

def repmgr_schema_name(conn):
    cur = conn.cursor()
    cur.execute("""SELECT nspname
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON (c.relnamespace=n.oid)
        WHERE n.nspname LIKE 'repmgr%' AND c.relname = 'nodes'""")

    repmgr_schema = None
    if cur.rowcount:
        repmgr_schema = cur.fetchone()[0]

    return repmgr_schema

def query_results(conn, query):
    res = []
    cur = conn.cursor()
    cur.execute(query)
    column_names = [desc[0] for desc in cur.description]
    for row in cur:
        res.append(dict(list(zip(column_names, row))))
    return res

def cast_interval(value, cur):
    if value is None:
        return None
    return str(value)

def register_casts():
    intervaloid = 1186
    interval = psycopg2.extensions.new_type(
        (intervaloid,), "interval", cast_interval
    )
    psycopg2.extensions.register_type(interval)

if __name__ == '__main__':
    main()
