import os
import inspect

import yaml

import tkinter as tk
from tkinter import ttk

from dosma import defaults
from dosma.cli import BASIC_TYPES, SUPPORTED_SCAN_TYPES
from dosma.gui.gui_utils.filedialog_reader import FileDialogReader


class TextWithVar(tk.Text):
    '''A text widget that accepts a 'textvariable' option'''

    def __init__(self, parent, *args, **kwargs):
        try:
            self._textvariable = kwargs.pop("textvariable")
        except KeyError:
            self._textvariable = None

        tk.Text.__init__(self, parent, *args, **kwargs)

        # if the variable has data in it, use it to initialize
        # the widget
        if self._textvariable is not None:
            self.insert("1.0", self._textvariable.get())

        # this defines an internal proxy which generates a
        # virtual event whenever text is inserted or deleted
        self.tk.eval('''
            proc widget_proxy {widget widget_command args} {

                # call the real tk widget command with the real args
                set result [uplevel [linsert $args 0 $widget_command]]

                # if the contents changed, generate an event we can bind to
                if {([lindex $args 0] in {insert replace delete})} {
                    event generate $widget <<Change>> -when tail
                }
                # return the result from the real widget command
                return $result
            }
            ''')

        # this replaces the underlying widget with the proxy
        self.tk.eval('''
            rename {widget} _{widget}
            interp alias {{}} ::{widget} {{}} widget_proxy {widget} _{widget}
        '''.format(widget=str(self)))

        # set up a binding to update the variable whenever
        # the widget changes
        self.bind("<<Change>>", self._on_widget_change)

        # set up a trace to update the text widget when the
        # variable changes
        if self._textvariable is not None:
            self._textvariable.trace("wu", self._on_var_change)

    def _on_var_change(self, *args):
        '''Change the text widget when the associated textvariable changes'''

        # only change the widget if something actually
        # changed, otherwise we'll get into an endless
        # loop
        text_current = self.get("1.0", "end-1c")
        var_current = self._textvariable.get()
        if text_current != var_current:
            self.delete("1.0", "end")
            self.insert("1.0", var_current)

    def _on_widget_change(self, event=None):
        '''Change the variable when the widget changes'''
        if self._textvariable is not None:
            self._textvariable.set(self.get("1.0", "end-1c"))


class Filepath(str):
    pass


TYPE_CAST = {bool: tk.BooleanVar, str: tk.StringVar, int: tk.IntVar, float: tk.DoubleVar}


def contains_filepath_keywords(param_name: str):
    fp_keywords = ['dir', 'path', 'directory', 'file']
    for k in fp_keywords:
        if k in param_name:
            return True

    return False


def convert_base_type_to_gui(param_name, param_type, param_default, root, **kwargs):
    balloon = None
    param_help = ''
    if 'balloon' in kwargs:
        balloon = kwargs.get('balloon')
    if 'param_help' in kwargs:
        param_help = kwargs.get('param_help')

    assert param_type in BASIC_TYPES, "type %s not in BASIC_TYPES" % param_type

    # add default value to param help
    has_default = param_default is not inspect._empty and param_default is not None

    type_var = TYPE_CAST[param_type]()
    if has_default:
        type_var.set(param_default)

    is_filepath = (param_type is str) and (not has_default) and contains_filepath_keywords(param_name)
    hbox = None
    if is_filepath:
        hbox = format_filepath_gui(root, param_name, type_var)
    elif param_type is bool:
        hbox = format_bool_gui(root, param_name, type_var)
    elif param_type is str:
        if 'options' in kwargs:
            hbox = format_list_gui(root, param_name, type_var, **kwargs)
        else:
            hbox = format_str_gui(root, param_name, type_var)

    if balloon and param_help:
        balloon.bind(hbox, param_help)

    return type_var


def format_filepath_gui(root, label, type_var, **kwargs):
    hbox = tk.Frame(root)
    hbox.pack(side='top', anchor='nw')

    l = tk.Label(hbox, text='%s: ' % label)
    l.pack(side='left', anchor='nw', padx=5)

    t = tk.Label(hbox, textvariable=type_var)
    t.pack(side='left', anchor='nw', padx=5)

    fd = FileDialogReader(type_var)
    fd_prompt = "Load %s" % label.lower()

    f_action = fd.get_filepath
    if 'dir' in label.lower():
        f_action = fd.get_dirpath

    b = ttk.Button(root, text=fd_prompt,
                   command=lambda: f_action(title=fd_prompt))

    b.pack(anchor='nw', pady=1)

    return hbox


def format_str_gui(root, label, type_var, **kwargs):
    hbox = tk.Frame(root)
    hbox.pack(side='top', anchor='nw')

    l = tk.Label(hbox, text='%s: ' % label)
    l.pack(side='left', anchor='nw', padx=5)

    t = TextWithVar(hbox, textvariable=type_var)
    t.pack(side='left', anchor='nw', padx=5)

    return hbox


def format_bool_gui(root, label, type_var, **kwargs):
    hbox = tk.Frame(root)
    hbox.pack(side='top', anchor='nw')

    l = tk.Label(hbox, text='%s: ' % label)
    l.pack(side='left', anchor='nw', padx=5)

    t = tk.Checkbutton(hbox, variable=type_var)
    t.pack(side='left', anchor='nw', padx=5)

    return hbox


def format_list_gui(root, label, type_var, **kwargs):
    options = kwargs.get('options')

    hbox = tk.Frame(root)
    hbox.pack(side='top', anchor='nw')

    l = tk.Label(hbox, text='%s: ' % label)
    l.pack(side='left', anchor='nw', padx=5)

    t = tk.OptionMenu(hbox, type_var, *options)
    t.pack(side='left', anchor='nw', padx=5)

    return hbox


class Aliases():
    """A pseudo-Singleton class implementation to track user-defined aliases.
    Do not instantiate this class. To modify/update preferences use the preferences module variable defined below.

    However, in the case this class is instantiated, a new object will be created, but all config properties will be
    shared among all instances. Meaning modifying the config in one instance will impact the preferences state in
    another instance.
    """
    _aliases_filepath = os.path.join(defaults._lib_dirpath, 'aliases.yml')
    __config = {}
    __key_list = []

    def __init__(self):
        # Load config and set information if config has not been initialized
        if not self.__config:
            with open(self._aliases_filepath, 'r') as f:
                self.__config = yaml.load(f)

            # Store all preference keys.
            self.__key_list = self._unroll_keys(self.config, '')

    def _unroll_keys(self, subdict: dict, prefix: str) -> list:
        """Recursive method to unroll keys."""
        pref_keys = []
        keys = subdict.keys()
        for k in keys:
            prefix_or_key = '%s/%s' % (prefix, k)
            val = subdict[k]
            if type(val) is dict:
                pref_keys.extend(self._unroll_keys(val, prefix_or_key))
            else:
                pref_keys.append(prefix_or_key)

        return pref_keys

    @staticmethod
    def _get_prefixes(prefix: str = ''):
        if not prefix:
            return ()

        r_prefixes = []
        prefixes = prefix.split('/')
        for p in prefixes:
            if p == '':
                continue
            r_prefixes.append(p)

        return r_prefixes

    def get(self, key, prefix: str = ''):
        """Get preference.
        :param key: Preference to peek. Can be full path preference.
        :type key: str
        :param prefix: prefix defining which sub-config to search (e.g. 'visualization/rcParams), defaults to ''
        :type prefix: str, optional

        :return: the preference.
        """
        return self.__get(self.__config, key, prefix)[0]

    def __get(self, b_dict: dict, key: str, prefix: str = ''):
        """Get preference.
        :param b_dict: Dictionary to search.
        :type b_dict: dict
        :param key: Preference to peek. Can be full path preference.
        :type key: str
        :param prefix: prefix defining which sub-config to search (e.g. 'visualization/rcParams), defaults to ''
        :type prefix: str, optional

        :return: the preference value, the subdictionary to search
        :rtype tuple of length 2
        """
        p_keys = self._get_prefixes(key)
        key = p_keys[-1]
        k_prefixes = list(p_keys[:-1])

        prefixes = list(self._get_prefixes(prefix))
        prefixes.extend(k_prefixes)

        subdict = b_dict
        for p in prefixes:
            subdict = subdict[p]

        num_keys = nested_lookup.get_occurrence_of_key(subdict, key)

        if num_keys == 0:
            raise KeyError('Key not \'%s \' found in prefix \'%s\'' % (key, prefix))
        if num_keys > 1:
            raise KeyError('Multiple keys \'%s \'found in prefix \'%s\'. Provide a more specific prefix.' % (key,
                                                                                                             prefix))

        return nested_lookup.nested_lookup(key, subdict)[0], subdict

    def set(self, key, value, prefix: str = ''):
        """Set preference.
        :param key: Preference to peek
        :type key: str
        :param value: value to set prefix.
        :type value: type of existing value
        :param prefix: prefix defining which sub-config to search (e.g. 'visualization/rcParams), defaults to ''
        :type prefix: str, optional

        :return: the preference.
        """
        val, subdict = self.__get(self.__config, key, prefix)

        # type of new value has to be the same type as old value
        if type(value) != type(val):
            try:
                value = type(val)(value)
            except (ValueError, TypeError) as e:
                raise TypeError('could not convert %s to %s: %s' % (type(value), type(val), value))

        p_keys = self._get_prefixes(key)
        key = p_keys[-1]
        nested_lookup.nested_update(subdict, key, value, in_place=True)

        # if param is an rcParam, update matplotlib
        if key in self.config['visualization']['matplotlib']['rcParams'].keys():
            matplotlib.rcParams.update({key: value})

    def save(self):
        with open(self._preferences_filepath, 'w') as f:
            yaml.dump(self.__config, f, default_flow_style=False)

    @property
    def config(self):
        """Get preferences configuration."""
        return self.__config

    # Make certain properties easily accessible through this class.
    @property
    def segmentation_batch_size(self) -> int:
        return self.get('/segmentation/batch.size')

    @property
    def visualization_use_vmax(self) -> bool:
        return self.get('/visualization/use.vmax')

    @property
    def mask_dilation_rate(self) -> float:
        return self.get('/registration/mask/dilation.rate')

    @property
    def mask_dilation_threshold(self) -> float:
        return self.get('/registration/mask/dilation.threshold')

    @property
    def fitting_r2_threshold(self):
        return self.get('/fitting/r2.threshold')

    @property
    def image_data_format(self):
        from dosma.data_io.format_io import ImageDataFormat
        return ImageDataFormat[self.get('/data/format')]

    def cmd_line_flags(self) -> dict:
        """Provide command line flags for changing preferences via command line.
        Not all preferences are listed here. Only those that should easily be set.
        All default values will be based on the current state of preferences, not the static state specified in yaml
        file.

        :return Preference keys with corresponding argparse kwarg dict
        :rtype: A dict of dicts.
        """
        with open(_preferences_cmd_line_filepath) as f:
            cmd_line_config = yaml.load(f)

        cmd_line_dict = {}
        for k in self.__key_list:
            try:
                argparse_kwargs, _ = self.__get(cmd_line_config, k)
            except KeyError:
                continue

            argparse_kwargs['default'] = self.get(k)
            argparse_kwargs['type'] = eval(argparse_kwargs['type'])
            cmd_line_dict[k] = argparse_kwargs

        return cmd_line_dict

    def __str__(self):
        return str(self.__config)