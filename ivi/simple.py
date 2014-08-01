"""

Python Interchangeable Virtual Instrument Library

Copyright (c) 2014 Kyle J. Temkin <ktemkin@binghamton.edu>
Copyright (c) 2012-2014 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

import ivi
import time
import types
import struct
from numpy import *


class CommandDrivenDevice(object):
    """ Base class for devcies which can easily be described via collections of SCPI commands. """


    def _add_scpi_property(self, property_name, get_command, set_command, response_parser, request_formatter, documentation=None):
        """ 
            Adds a new property to the given IVI device by providing the SCPI commands used to get and set that property. Can greatly simplify
            constructing new SCPI devices.

            property_name:      The name of the property to be added, in the same format accepted by ivi.add_property.
            get_command:        The SCPI command used to read the property, as a string. (e.g. "VOLT?").
            set_command:        The SCPI command used to write the property, as a string. (e.g. "VOLT").
            response_parser:    A function which will be called on the result before it is returned. Intended to be used
                                to parse the respone from the device into a more pythonic form.
            request_formatter:  A function which will be called on the user value before it is transmitted to the device. 
                                Intended to be used to correctly format the given argument for transmission.
            documentation:      A documentation string to be added to the property, for use with python's built-in help.
        
        """
        
        #Determine if the given property is an indexed property, from its name.
        is_indexed = self._property_is_indexed(property_name)

        #Get the relevant functions to handle the SCPI property... 
        getter, setter = self._generate_scpi_methods(property_name, get_command, set_command, response_parser, request_formatter, is_indexed)

        #... and add the property to the current object.
        ivi.add_property(self, property_name, getter, setter, None, documentation)


    def _add_simple_scpi_property(self, property_name, set_command, response_parser, request_formatter):
        """ 
            Convenience case of add_scpi_property in which the set and get command are the same (plus a question mark
            for the query command). 
        """
        self._add_scpi_property(property_name, set_command + "?", set_command, response_parser, request_formatter)


    def _implement_scpi_methods(self, method_suffix, get_command, set_command, response_parser, request_formatter, indexed = False):
        """
            Creates a getter and setter function for a previously-implemented pair of IVI properties. This is typically used to implement a getter/setter
            pair inherited from a parent IVI class.

            property_name:      The name of the property to be added, in the same format accepted by ivi.add_property.
            get_command:        The SCPI command used to read the property, as a string. (e.g. "VOLT?").
            set_command:        The SCPI command used to write the property, as a string. (e.g. "VOLT").
            response_parser:    A function which will be called on the result before it is returned. Intended to be used
                                to parse the respone from the device into a more pythonic form.
            request_formatter:  A function which will be called on the user value before it is transmitted to the device. 
                                Intended to be used to correctly format the given argument for transmission.
            indexed:            True iff the previously-implemented IVI properties are indexed.
        """

        #Get the relevant functions to handle the SCPI property... 
        getter, setter = self._generate_scpi_methods(method_suffix, get_command, set_command, response_parser, request_formatter, indexed)

        #... and attach them to the expected place in the current module. 
        setattr(self, "_get" + method_suffix, getter)
        setattr(self, "_set" + method_suffix, setter)


    def _implement_simple_scpi_methods(self, method_suffix, set_command, response_parser, request_formatter, indexed = False):
        """ 
            Convenience case of implement_SCPI_methods in which the set and get command are the same (plus a question mark
            for the query command). 
        """
        self._implement_scpi_methods(method_suffix, set_command + "?", set_command, response_parser, request_formatter, indexed)



    def _generate_scpi_methods(self, property_name, get_command, set_command, response_parser, request_formatter, indexed = False):
        """ 
            Generates a pair of SCPI-command dirven control methods which can be used to get/set simple controls
            on the relevant device.
        """

        #Define an inner function whcih will handle assignment to the property.
        def set_indexed_property(self, index, value):

            if index != -1:
            
                #Determine the relevant array index for channel index given....
                index = ivi.get_index(self._output_name, index)

                #... and adjust the command to contain the channel number, if necessary.
                command = self._get_command_modified_for_channel(set_command, index)

            #Convert the specified value into correctly formatted request.
            request = request_formatter(value)

            #If we're not performing a simulation, perform the command itself.
            if not self._driver_operation_simulate:
                self._write(command + " " + request)

            #... and update the cache accordingly.
            #getattr(self, property_name)[index] = value
            self._set_cached_property(property_name, value, index)
            self._set_cache_valid(tag=property_name, index=index)


        def set_simple_property(self, value):
            self.set_indexed_property(-1, value)


        #Define an inner function which handles the property's read.
        def get_indexed_property(self, index):
            nonlocal get_command, response_parser

            if index != -1:

                #Determine the relevant array index for channel index given.
                index = ivi.get_index(self._output_name, index)

                #adjust the command to contain the channel number, if necessary.
                command = self._get_command_modified_for_channel(get_command, index)

            #If we're not simulating the device, and nothing has changed, run the relevant command.
            if not self._driver_operation_simulate and not self._get_cache_valid(tag=property_name, index=index):

                #Perform the raw query...
                response = self._ask(command)
                response = self._adjust_response_for_channel(response, index)
                response = response_parser(response)
               
                #... and update the cache.
                self._set_cached_property(property_name, response, index)

            #Return the relevant cached property.
            return self._get_cached_property(property_name, index)

        def get_simple_property(self):
            self.get_indexed_property(-1)


        #Create methodized versions of these inner functions, bound to the current object. 
        method_get_indexed_property = types.MethodType(get_indexed_property, self)
        method_set_indexed_property = types.MethodType(set_indexed_property, self)
        method_get_simple_property  = types.MethodType(get_simple_property, self)
        method_set_simple_property  = types.MethodType(set_simple_property, self)


        #If we have an indexed proeprty, return the indexed pair of methods...
        if indexed:
            return (method_get_indexed_property, method_set_indexed_property)

        #... otherwise, return the simple ones.
        else:
            return (method_get_simple_property, method_set_simple_property)
           

    def _set_cached_property(self, property_name, value, index=-1):
        """ Sets an internally cached property. """

        #If we have an indexed property, get the core property object,
        #and set the appropriate index.
        if index != -1:

            #If this indexed property doesn't yet exist, create it implicitly.
            if not hasattr(self, property_name):
                setattr(self, property_name, list())

            #Grab the cached version of the indexed property.
            cache = getattr(self, property_name)

            #... and extend the list to the necessary length, if needed.
            while len(cache) < index + 1:
                cache.append(None)

            cache[index] = value
            self._set_cache_valid(tag=property_name, index=index)

        #Otherwise, set the parameter itself.
        else:
            setattr(self, property_name, value)
            self._set_cache_valid(tag=property_name)


    def _get_cached_property(self, property_name, index=-1):
        """ Gets the internally cached value of a given property. """

        #Get the value of the property itself...
        result = getattr(self, property_name)

        #... and, if we have an indexed property, resolve the index.
        if index != -1:
            result = result[index]

        return result


    def _property_is_indexed(self, property_name):
        """ Returns true iff the given property name corresponds to an indexed property. """
        return property_name.find('[') > 0


    def _get_command_modified_for_channel(self, command, channel):
        """
            Adjusts the given command to address the given channel number. This default
            implementation returns the command unmodified; and is suitable for devices
            with only one output.
        """

        return command


    def _adjust_response_for_channel(self, response, channel):
        """
            Adjusts the given response to remove any channel-number related prefixes or
            suffixes, as returned by some devices. This default implementation returns
            the response directly.
        """

        return response




