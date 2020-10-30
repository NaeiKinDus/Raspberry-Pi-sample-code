# -*- coding: utf-8 -*-
"""
Routines and classes to interact with I2C sensors from Atlas Scientific.

This module exports a generic class that handles all I2C sensors from Atlas Scientific.
It has been tested against EZO sensors including:
- DO
- EC
- Flow
- ORP
- PH
- RTD
"""

import copy
import fcntl
import io
import time
from typing import List, NoReturn, Optional, Tuple


class AtlasI2C:
    """I2C class used to interact with Atlas devices."""

    # the timeout needed to query readings and calibrations
    LONG_TIMEOUT = 1.5
    # timeout for regular commands
    SHORT_TIMEOUT = .3
    # the default bus for I2C on the newer Raspberry Pis,
    # certain older boards use bus 0
    DEFAULT_BUS = 1
    # the default address for the sensor
    DEFAULT_ADDRESS = 98
    # commands that need to use the LONG_TIMEOUT value
    LONG_TIMEOUT_COMMANDS = ("R", "CAL")
    # commands with no return data
    SLEEP_COMMANDS = ("SLEEP",)
    # address for the slave, see i2c-dev.h
    _I2C_SLAVE_ADDR = 0x703

    def __init__(
            self,
            address: Optional[int] = None,
            moduletype: Optional[str] = '',
            name: Optional[str] = '',
            bus: Optional[int] = None
    ):
        """
        Constructor for the class.

        Open two file streams, one for reading and one for writing
        the specific I2C channel is selected with bus
        it is usually 1, except for older revisions where its 0
        wb and rb indicate binary read and write.

        :param address: I2C address of the sensor
        :type address: Optional[int]
        :param moduletype: a user defined friendly sensor type, not stored on the sensor
        :type moduletype: str
        :param name: a user defined friendly name, not stored on the sensor
        :type name: str
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
    def long_timeout(self) -> float:
        """Returns _long_timeout."""
        return self._long_timeout

    @property
    def short_timeout(self) -> float:
        """Returns _short_timeout."""
        return self._short_timeout

    @property
    def name(self) -> str:
        """Returns _name."""
        return self._name

    @property
    def address(self) -> int:
        """Returns _address."""
        return self._address

    @property
    def moduletype(self) -> str:
        """Returns _module."""
        return self._module

    @staticmethod
    def get_response(raw_data: bytes) -> bytes:
        """
        Sanitizes the response.

        :param raw_data: raw data retrieved from the sensor
        :type raw_data: bytes
        :return: sanitized response as a list of characters
        :rtype: List[int]
        """
        return bytes([i for i in raw_data if i != 0])

    @staticmethod
    def is_valid(response: bytes) -> Tuple[bool, int]:
        """
        Determines if a response is valid and gets related error code.

        :param response: response retrieved from the sensor
        :type response: str
        :return: a tuple with whether the response is valid
            and the related error code if it is not
        :rtype: Tuple[bool, int]
        """
        error_code = None
        if len(response) > 0:
            error_code = int(response[0])
            if error_code == 1:
                return True, error_code
        return False, error_code

    @staticmethod
    def handle_raspi_glitch(response: bytes) -> List[str]:
        """
        Handle an MSB/LSB RPi glitch.

        Change MSB to 0 for all received characters except the first
        and get a list of characters.
        NOTE: having to change the MSB to 0 is a glitch in the raspberry pi,
        and you shouldn't have to do this!

        :param response: response retrieved from the sensor
        :type response: bytes
        :return: a list of converted characters making up the proper sensor response
        :rtype: List[str]
        """
        return list(map(lambda x: chr(x & ~0x80), list(response)))

    def set_i2c_address(self, addr: int) -> NoReturn:
        """
        Set I2C address.

        Set the I2C communications to the slave specified by the address
        the commands for I2C dev using the ioctl functions are specified in
        the i2c-dev.h file from i2c-tools.

        :param addr: Address of the I2C device
        :type addr: int
        """
        fcntl.ioctl(self.file_read, self._I2C_SLAVE_ADDR, addr)
        fcntl.ioctl(self.file_write, self._I2C_SLAVE_ADDR, addr)
        self._address = addr

    def write(self, cmd: str) -> int:
        """
        Appends the null character and sends the string over I2C.

        :param cmd: command to send to the device
        :type cmd: str
        :return: number of bytes written
        :rtype: int
        """
        cmd += "\00"
        return self.file_write.write(cmd.encode('latin-1'))

    def get_device_info(self) -> str:
        """
        Get device information.

        Returns a string identifying the sensor in the form of:
            <module_name> <i2c_addr>[ <sensor_name>]

        :return: identifier of the sensor
        :rtype: str
        """
        if not self._name:
            return self._module + " " + str(self.address)
        else:
            return self._module + " " + str(self.address) + " " + self._name

    def read(self, num_of_bytes: int = 31) -> Tuple[int, Optional[str]]:
        """
        Reads a specified number of bytes from I2C, then parses and displays the result.

        :param num_of_bytes: bytes to be read from the sensor
        :type num_of_bytes: int
        :return: a tuple containing an error code (0 if OK) and the read data, if applicable.
        :rtype: Tuple[int, Optional[str]]
        """
        raw_data = self.file_read.read(num_of_bytes)
        response = self.get_response(raw_data=raw_data)
        is_valid, error_code = AtlasI2C.is_valid(response=response)

        if is_valid:
            char_list = AtlasI2C.handle_raspi_glitch(response[1:])
            return 0, str(''.join(char_list))
        else:
            return error_code, None

    def get_command_timeout(self, command: str) -> Optional[float]:
        """
        Returns the read time expected for a specific command.

        :param command: the command to check for
        :type command: str
        :return: Optional[float]
        """
        if command.upper().startswith(self.LONG_TIMEOUT_COMMANDS):
            return self._long_timeout
        elif not command.upper().startswith(self.SLEEP_COMMANDS):
            return self.short_timeout
        return None

    def query(self, command: str) -> Optional[Tuple[int, Optional[str]]]:
        """
        Send a command to the sensor.

        Write a command to the board, wait the correct timeout,
        and read the response.

        :param command: command to be sent to the device
        :type command: str
        :return: a tuple containing an error code and the device's response
        :rtype: Optional[Tuple[int, Optional[str]]]
        """
        self.write(command)
        current_timeout = self.get_command_timeout(command=command)
        if not current_timeout:
            # No return, command was "Sleep"
            return None
        else:
            time.sleep(current_timeout)
            return self.read()

    def close(self) -> NoReturn:
        """Close opened file descriptors."""
        self.file_read.close()
        self.file_write.close()

    def list_i2c_devices(self) -> List[int]:
        """
        Walk existing I2C devices and return available addresses.

        :return: a list of used I2C addresses
        :rtype: List[int]
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
