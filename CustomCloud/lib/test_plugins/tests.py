from jinja2 import Undefined

# This filter takes a container and a subkey ('x.y.z', or [x,y,z]) and returns
# true if the subkey exists in the container, or false if any of the levels is
# undefined.

def has_subkey(container, keys):
    try:
        v = container
        if isinstance(keys, basestring):
            keys = keys.split('.')
        for key in keys:
            v = v.get(key)
        return v and True or False
    except KeyError:
        return False

class TestModule(object):
    def tests(self):
        return {
            'has_subkey': has_subkey,
        }
