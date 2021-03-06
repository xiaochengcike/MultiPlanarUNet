from ruamel.yaml import YAML
import os
import re


class YAMLHParams(dict):
    def __init__(self, yaml_path, logger=None, no_log=False, **kwargs):
        dict.__init__(self, **kwargs)

        # Set logger or default print
        self.logger = logger if logger is not None else print

        # Set YAML path
        self.yaml_path = os.path.abspath(yaml_path)
        self.string_rep = ""
        self.project_path = os.path.split(self.yaml_path)[0]
        if not os.path.exists(self.yaml_path):
            raise OSError("YAML path '%s' does not exist" % self.yaml_path)
        else:
            with open(self.yaml_path, "r") as yaml_file:
                for line in yaml_file:
                    self.string_rep += line
            hparams = YAML(typ="safe").load(self.string_rep)

        # Set dict elements
        self.update({k: hparams[k] for k in hparams if k[:4] != "__CB"})

        # Log basic information here...
        self.no_log = no_log
        if not self.no_log:
            self.logger("YAML path:    %s" % self.yaml_path)

    @property
    def groups(self):
        groups_re = re.compile(r"\n^(?![ \n])(.*?:.*?\n)", re.MULTILINE)
        start, groups = 0, []
        for iter in re.finditer(groups_re, self.string_rep):
            end = iter.start(0)
            groups.append(self.string_rep[start:end])
            start = end
        groups.append(self.string_rep[start:])
        return groups

    def get_group(self, group_name):
        groups = [g.lstrip("\n").lstrip(" ") for g in self.groups]
        return groups[[g.split(":")[0] for g in groups].index(group_name)]

    def add_group(self, yaml_string):
        group_name = yaml_string.lstrip(" ").lstrip("\n").split(":")[0]

        # Set dict version in memory
        self[group_name] = YAML().load(yaml_string)

        # Add pure yaml string to string representation
        self.string_rep += "\n" + yaml_string

    def delete_group(self, group_name):
        self.string_rep = self.string_rep.replace(self.get_group(group_name), "")
        del self[group_name]

    def get_from_anywhere(self, key):
        found = []
        for group in self:
            if key in group:
                found.append((group, group[key]))
        if len(found) > 1:
            self.logger("[ERROR] Found key '%s' in multiple groups (%s)" %
                        (key, [g[0] for g in found]))
        elif len(found) == 0:
            return None
        else:
            return found[0][1]

    def log(self):
        for item in self:
            self.logger("%s\t\t%s" % (item, self[item]))

    def set_value(self, subdir, name, value, update_string_rep=True,
                  overwrite=False):

        exists = name in self[subdir]
        cur_value = self[subdir].get(name)
        if not exists or (cur_value is None or cur_value is False) or overwrite:
            if not self.no_log:
                self.logger("Setting value '%s' in subdir '%s' with "
                            "name '%s'" % (value, subdir, name))

            # Set the value in memory
            name_exists = name in self[subdir]
            self[subdir][name] = value

            # Update the string representation as well?
            if update_string_rep:
                # Get relevant group
                l = len(subdir)
                group = [g for g in self.groups if g.lstrip()[:l] == subdir][0]

                # Replace None or False with the new value within the group
                pattern = re.compile(r"%s:[ ]+(.*)[ ]?\n" % name)

                # Find and insert new value
                def rep_func(match):
                    """
                    Returns the full match with the
                    capture group replaced by str(value)
                    """
                    return match.group().replace(match.groups(1)[0], str(value))
                new_group = re.sub(pattern, rep_func, group)

                if not name_exists:
                    # Add the field if not existing already
                    assert new_group == group  # No changes should occur
                    new_group = new_group.strip("\n")
                    temp = new_group.split("\n")[1]
                    indent = len(temp) - len(temp.lstrip())
                    new_field = (" " * indent) + "%s: %s" % (name, value)
                    new_group = "\n%s\n%s\n" % (new_group, new_field)

                # Update string representation
                self.string_rep = self.string_rep.replace(group, new_group)
            return True
        else:
            self.logger("Attribute '%s' in subdir '%s' already set "
                        "with value '%s'" % (name, subdir, cur_value))
            return False

    def save_current(self, out_path=None):
        # Write to file
        out_path = os.path.abspath(out_path or self.yaml_path)
        if not self.no_log:
            self.logger("Saving current YAML configuration to file:\n", out_path)
        with open(out_path, "w") as out_f:
            out_f.write(self.string_rep)
