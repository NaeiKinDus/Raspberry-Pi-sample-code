# -*- coding: utf-8 -*-

import io
import sys
import fcntl
import time
import copy


class AtlasI2C:
    """
    I2C class used to communicate with Atlas sensors
    """
    # the timeout needed to query readings and calibrations
    LONG_TIMEOUT = 1.5
    # timeout for regular commands
    SHORT_TIMEOUT = .3
    # the default bus for I2C on the newer Raspberry Pis,
    # certain older boards use bus 0
    DEFAULT_BUS = 1
    # the default address for the sensor
    DEFAULT_ADDRESS = 98
    LONG_TIMEOUT_COMMANDS = ("R", "CAL")
    SLEEP_COMMANDS = ("SLEEP",)
    # address for the slave, see i2c-dev.h
    _I2C_SLAVE_ADDR = 0x703

    def __init__(self, address=None, moduletype="", name="", bus=None):
        """
        open two file streams, one for reading and one for writing
        the specific I2C channel is selected with bus
        it is usually 1, except for older revisions where its 0
        wb and rb indicate binary read and write
        """
        self._address = address or self.DEFAULT_ADDRESS
        self.bus = bus or self.DEFAULT_BUS
        self._long_timeout = self.LONG_TIMEOUT
        self._short_timeout = self.SHORT_TIMEOUT
        self.file_read = io.open(
            file="/dev/i2c-{}".format(self.bus),
            mode="rb",
            buffering=0
        )
        self.file_write = io.open(
            file="/dev/i2c-{}".format(self.bus),
            mode="wb",
            buffering=0
        )
        self.set_i2c_address(self._address)
        self._name = name
        self._module = moduletype

    @property
    def long_timeout(self):
        return self._long_timeout

    @property
    def short_timeout(self):
        return self._short_timeout

    @property
    def name(self):
        return self._name

    @property
    def address(self):
        return self._address

    @property
    def moduletype(self):
        return self._module

    @staticmethod
    def app_using_python_two():
        return sys.version_info[0] < 3

    def set_i2c_address(self, addr):
        """
        set the I2C communications to the slave specified by the address
        the commands for I2C dev using the ioctl functions are specified in
        the i2c-dev.h file from i2c-tools
        """
        fcntl.ioctl(self.file_read, self._I2C_SLAVE_ADDR, addr)
        fcntl.ioctl(self.file_write, self._I2C_SLAVE_ADDR, addr)
        self._address = addr

    def write(self, cmd):
        """
        appends the null character and sends the string over I2C
        """
        cmd += "\00"
        self.file_write.write(cmd.encode('latin-1'))

    def handle_raspi_glitch(self, response):
        """
        Change MSB to 0 for all received characters except the first
        and get a list of characters
        NOTE: having to change the MSB to 0 is a glitch in the raspberry pi,
        and you shouldn't have to do this!
        """
        if self.app_using_python_two():
            return list(map(lambda x: chr(ord(x) & ~0x80), list(response)))
        else:
            return list(map(lambda x: chr(x & ~0x80), list(response)))

    def get_response(self, raw_data):
        if self.app_using_python_two():
            return [i for i in raw_data if i != '\x00']
        else:
            return raw_data

    def response_valid(self, response):
        valid = True
        error_code = None
        if len(response) > 0:
            if self.app_using_python_two():
                error_code = str(ord(response[0]))
            else:
                error_code = str(response[0])

            if error_code != '1':
                valid = False

        return valid, error_code

    def get_device_info(self):
        if not self._name:
            return self._module + " " + str(self.address)
        else:
            return self._module + " " + str(self.address) + " " + self._name

    def read(self, num_of_bytes=31):
        """
        reads a specified number of bytes from I2C, then parses and displays the result
        """
        raw_data = self.file_read.read(num_of_bytes)
        response = self.get_response(raw_data=raw_data)
        is_valid, error_code = self.response_valid(response=response)

        if is_valid:
            char_list = self.handle_raspi_glitch(response[1:])
            return "Success " + self.get_device_info() + ": " + str(''.join(char_list))
        else:
            return "Error " + self.get_device_info() + ": " + error_code

    def get_command_timeout(self, command):
        if command.upper().startswith(self.LONG_TIMEOUT_COMMANDS):
            return self._long_timeout
        elif not command.upper().startswith(self.SLEEP_COMMANDS):
            return self.short_timeout
        return None

    def query(self, command):
        """
        write a command to the board, wait the correct timeout,
        and read the response
        """
        self.write(command)
        current_timeout = self.get_command_timeout(command=command)
        if not current_timeout:
            return "sleep mode"
        else:
            time.sleep(current_timeout)
            return self.read()

    def close(self):
        self.file_read.close()
        self.file_write.close()

    def list_i2c_devices(self):
        """
        save the current address so we can restore it after
        """
        prev_addr = copy.deepcopy(self._address)
        i2c_devices = []
        for i in range(0, 128):
            try:
                self.set_i2c_address(i)
                self.read(1)
                i2c_devices.append(i)
            except IOError:
                pass
        # restore the address we were using
        self.set_i2c_address(prev_addr)

        return i2c_devices
