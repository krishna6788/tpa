LXD
===

## WIP

```
instance_defaults:
  platform: lxd

instances:
    - node: 1
      Name: pear
      mode: pull
      server: https://cloud-images.ubuntu.com/releases
      alias: "16.04"
      protocol: simplestreams
      architecture: x86_64
      disk_space: 10GB          # Container's Disk limit
      memory: 2GB               # Container's Memory limit
      nesting: "true"           # Container's security.nesting enabled
      storage_pool: lxd
      network: lxdbr0
      ip_address: 10.44.156.2    # static IPv4 address according with lxdbr0 subnet
      profile: default
      status: started
      role: primary
      vars:
        work_mem: 16MB
        postgres_data_dir: /var/lib/postgresql/data
```