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

import time
import types
import struct
from numpy import *

from usb.core import USBError

from .. import ivi
from .. import fgen
from .. import simple
from .. import rfsiggen

StandardWaveformMapping = {
        'sine': 'sin',
        'square': 'squ',
        'ramp': 'ramp',
        'triangle': 'ramp',
        'pulse': 'puls',
        'noise': 'nois',
        'dc': 'dc',
        'arb': 'user',
        'user': 'user'
        }

class rigolDG1022(ivi.Driver, simple.CommandDrivenDevice, 
                  fgen.Base, fgen.StdFunc, fgen.ArbWfm, fgen.Burst):
                  
    """
        Rigol DG1022-series arbitrary waveform generator driver

        TODO:
            -Implement StartTrigger
            -Implement StopTrigger
            -Implement AwfmBinary
    """
    
    def __init__(self, *args, **kwargs):
        self.__dict__.setdefault('_instrument_id', '')


        self._define_SCPI_commands()
        super(rigolDG1022, self).__init__(*args, **kwargs)

        self._output_count = 2
       
        #TODO: Update me!
        self._arbitrary_sample_rate = 0
        self._arbitrary_waveform_number_waveforms_max = 0
        self._arbitrary_waveform_size_max = 256*1024
        self._arbitrary_waveform_size_min = 64
        self._arbitrary_waveform_quantum = 8
        
        self._arbitrary_sequence_number_sequences_max = 0
        self._arbitrary_sequence_loop_count_max = 0
        self._arbitrary_sequence_length_max = 0
        self._arbitrary_sequence_length_min = 0
        
        self._catalog_names = list()
        
        self._arbitrary_waveform_n = 0
        self._arbitrary_sequence_n = 0
        
        self._identity_description = "Rigol DG1022 series arbitrary waveform generator driver"
        self._identity_identifier = ""
        self._identity_revision = ""
        self._identity_vendor = ""
        self._identity_instrument_manufacturer = "Rigol"
        self._identity_instrument_model = ""
        self._identity_instrument_firmware_revision = ""
        self._identity_specification_major_version = 5
        self._identity_specification_minor_version = 0
        self._identity_supported_instrument_models = ['DG1022', 'DG1022U', 'DG1022A']

        #Pull in the list of available Standard Waveforms.
        self._output_standard_waveform_mapping = StandardWaveformMapping

        #On some systems, the DG1022 won't reliably communicate. In these cases, a hackish
        #solution may be to repeatedly retry until the communcation goes through. Ugly, but effecitve.
        self.automatic_retry_count = 1 

        
        self._init_outputs()

    
    #
    # "Quirk" necessary as some Rigol devices don't properly comply with the USB(TMC) spec,
    # and thus sometimes must be queried more than once. If "automatic_retry_count" is set, the
    # device will automatically be retriedup to that many times.
    #
    def _ask(self, command):

        last_error = None

        #Retry up to N times...
        for _ in range(self.automatic_retry_count):
            try:
                return super(rigolDG1022, self)._ask(command)
            except USBError as error:
                last_error = error

        #If we weren't able to succeed in the N tries, raise the last error.
        raise last_error



    def _define_SCPI_commands(self):
        self._define_function_generator_commands()
        self._define_standard_wafeform_commands()
        self._define_burst_commands()

        self._add_custom_commands()


    def _define_function_generator_commands(self):

        #ivi.add_property(self, 'outputs[].name', self._get_output_name,
        #ivi.add_property(self, 'outputs[].operation_mode', self._get_output_operation_mode, self._set_output_operation_mode,
        #ivi.add_property(self, 'outputs[].output_mode',

        self._implement_simple_scpi_methods('_output_enabled', 'OUTP', self._parse_on_off, self._format_on_off, True)
        self._implement_simple_scpi_methods('_output_impedance', 'OUTP:LOAD', float, str, True)
        self._implement_scpi_methods('_output_reference_clock_source', None, 'SYST:CLKSRC', float, str, True)

    def _define_standard_wafeform_commands(self):
        self._implement_simple_scpi_methods('_output_standard_waveform_amplitude', "VOLT", float, str, True)
        self._implement_simple_scpi_methods('_output_standard_waveform_dc_offset', "VOLT:OFFS", float, str, True)
        self._implement_simple_scpi_methods('_output_standard_waveform_start_phase', "PHASE", float, str, True)
        self._implement_simple_scpi_methods('_output_standard_waveform_frequency', "FREQ", float, str, True)
        self._implement_simple_scpi_methods('_output_standard_waveform_waveform', "FUNC", self._parse_waveform_name, self._format_waveform_name, True)

        #These intermediary methods are called by delegators, which handle the appropriate actions based
        #on which function we're generating.
        self._implement_simple_scpi_methods('_output_standard_waveform_duty_cycle_square', "FUNC:SQU:DCYC", float, str, True) 
        self._implement_simple_scpi_methods('_output_standard_waveform_duty_cycle_pulse',  "PULS:DCYC", float, str, True)  


    def _get_output_standard_waveform_duty_cycle_high(self, index):
        """ 
            Delegator function which calls the appropriate getter for the duty cycle,
            given the active waveform.
        """

        #If we're currnetly producing a square wave, get the square wave's duty cycle. 
        if self.outputs[index].standard_waveform.waveform == 'square':
            return self._get_output_standard_waveform_duty_cycle_square(index)

        #... otherwise, return the pulse's duty cycle.
        else:
            return self._get_output_standard_waveform_duty_cycle_pulse(index)

    
    def _set_output_standard_waveform_duty_cycle_high(self, index, value):
        """ 
            Delegator function which calls the appropriate setter for the duty cycle,
            given the active waveform.
        """

        #If we're currnetly producing a square wave, get the square wave's duty cycle. 
        if self.outputs[index].standard_waveform.waveform == 'square':
            return self._set_output_standard_waveform_duty_cycle_square(index, value)

        #... otherwise, return the pulse's duty cycle.
        else:
            return self._set_output_standard_waveform_duty_cycle_pulse(index, value)



    def _add_custom_commands(self):
        """
            Add commands supported by the DG1022 which aren't supported by our base classes.
        """
        self._add_simple_scpi_property('outputs[].standard_waveform.symmetry', 'FUNC:RAMP:SYMM', float, str)

        #Pulse commands:
        self._add_simple_scpi_property('outputs[].pulse.period', 'PULS:PER', float, str)
        self._add_simple_scpi_property('outputs[].pulse.width', 'PULS:WID', float, str)
        self._add_simple_scpi_property('outputs[].pulse.duty_cycle_high', 'PULS:DCYC', float, str)


    def _define_burst_commands(self):
        self._implement_simple_scpi_methods('_output_burst_count', "BURS:NCYC", float, str, True)


    @staticmethod
    def _parse_on_off(value):
        """ Parses a query which should return ON or OFF as a boolean expression. """
        return value.lower() != "off"

    @staticmethod
    def _format_on_off(value):
        """ Converts a boolean into an ON/OFF for a SCPI request. """
        return "ON" if value else "OFF"


    def _parse_waveform_name(self,value):
        """ Converts a function-generator encoded wafeform name to a python-ivi human readable standard. """

        #Attmempt to look up the given waveform name in the relevant dictionary.
        for long_form, short_form in self._output_standard_waveform_mapping.items():
            if short_form.lower() == value.lower():
                return value

        #If it doesn't exist, return the function-generator name directly,
        return value


    def _format_waveform_name(self, value):
        """ Converts a human-readable name to a function-generator comprehensible name. """

        #If this is a known human readable value, convert it to the function generator "short form".
        if value in self._output_standard_waveform_mapping:
            return self._output_standard_waveform_mapping[value]

        #Otherwise, return the waveform value unmodified.
        return value



    def _get_command_modified_for_channel(self, command, index):
        """ Modifies the given command to take place on the provided channel index, in Rigol format. """

        #If this is the first channel
        if index <= 0:
            return command

        #Compute the channel number, which is one greater than the index.
        channel_number = index + 1

        #If this is a query, we'll need to add the channel name before the question mark...
        if "?" in command:
            command = command.replace("?", ":CH" + str(channel_number) + "?", 1)

        #... otherwise, we can just append it.
        else:
            command = command + ":CH" + str(channel_number)

        #Return the modified command.
        return command


    def _adjust_response_for_channel(self, response, index):
        """
            Adjusts command responses to remove the channel number, where applicable.
            The DG1022 responds to the second-channel (and etc.)
        """

        channel_number = index + 1

        #If this is a channel-prefixed response, remove the channel number.
        if response.startswith('CH' + str(channel_number) + ':'):
            response = response[4:]

        #... and return the response otherwise unmodified.
        return response


    def initialize(self, resource = None, id_query = False, reset = False, **keywargs):
        "Opens an I/O session to the instrument."
        
        super(rigolDG1022, self).initialize(resource, id_query, reset, **keywargs)
        
        # interface clear
        if not self._driver_operation_simulate:
            self._clear()
        
        # check ID
        if id_query and not self._driver_operation_simulate:
            id = self.identity.instrument_model
            id_check = self._instrument_id
            id_short = id[:len(id_check)]
            if id_short != id_check:
                raise Exception("Instrument ID mismatch, expecting %s, got %s", id_check, id_short)
        
        # reset
        if reset:
            self.utility_reset()


    @classmethod
    def first_connected_device(cls):
        """Convenience method which returns the first connected DG1022."""
        return cls("USB0::0x0400::0x09C4::INSTR")


    def _load_id_string(self):
        if self._driver_operation_simulate:
            self._identity_instrument_manufacturer = "Not available while simulating"
            self._identity_instrument_model = "Not available while simulating"
            self._identity_instrument_firmware_revision = "Not available while simulating"
        else:
            lst = self._ask("*IDN?").split(",")
            self._identity_instrument_manufacturer = lst[0]
            self._identity_instrument_model = lst[1]
            self._identity_instrument_firmware_revision = lst[3]
            self._set_cache_valid(True, 'identity_instrument_manufacturer')
            self._set_cache_valid(True, 'identity_instrument_model')
            self._set_cache_valid(True, 'identity_instrument_firmware_revision')

    def _reload_id_string_if_necessary(self):
        """ Reloads the device's identification, if it's out of date. """

        if not self._get_cache_valid():
            self._load_id_string()

    def _get_identity_instrument_manufacturer(self):
        """ Returns the device's manufacturer. """

        self._reload_id_string_if_necessary()
        return self._identity_instrument_manufacturer
    
    def _get_identity_instrument_model(self):
        self._reload_id_string_if_necessary()
        return self._identity_instrument_model
    
    def _get_identity_instrument_firmware_revision(self):
        self._reload_id_string_if_necessary()
        return self._identity_instrument_firmware_revision
    
    def _utility_disable(self):
        pass
    
    def _utility_error_query(self):
        """ Returns the most recently experienced error. """

        #Retrieve the device's most recent error message...
        most_recent_error = self._ask("SYST:ERR?")

        #... split it into a code and a message.
        error_code, error_message = most_recent_error.split(',')

        #Parse the code and numbers.
        error_code = int(error_code)
        error_message = error_message.replace('"', '')

        return (error_code, error_message)
    
    def _utility_lock_object(self):
        pass
    
    def _utility_reset(self):
        if not self._driver_operation_simulate:
            self._write("*RST")
            self.driver_operation.invalidate_all_attributes()
    
    def _utility_reset_with_defaults(self):
        self._utility_reset()
    
    def _utility_unlock_object(self):
        pass
    
    #def _init_outputs(self):
    #    try:
    #        super(rigolDG1022, self)._init_outputs()
    #    except AttributeError:
    #        pass
    #    
    #    self._output_enabled = list()

    #    for i in range(self._output_count):
    #        self._output_enabled.append(False)
         
         
    def  _load_catalog(self):
         self._catalog = list()
         self._catalog_names = list()
         if not self._driver_operation_simulate:
            raw = self._ask("DATA:CAT?").lower()
            raw = raw.split(' ', 1)[1]
            
            l = raw.split(',')
            l = [s.strip('"') for s in l]
            self._catalog = [l[i:i+3] for i in range(0, len(l), 3)]
            self._catalog_names = [l[0] for l in self._catalog]
    
    
    def _get_output_arbitrary_waveform(self, index):

        #TODO: This should be from cache, only?

        index = ivi.get_index(self._output_name, index)
        if not self._driver_operation_simulate and not self._get_cache_valid(index=index):
            resp = self._ask(":ch%d:waveform?" % (index+1)).split(' ', 1)[1]
            self._output_arbitrary_waveform[index] = resp.strip('"').lower()
            self._set_cache_valid(index=index)
        return self._output_arbitrary_waveform[index]
    
    def _set_output_arbitrary_waveform(self, index, value):
        index = ivi.get_index(self._output_name, index)
        value = str(value).lower()
        # extension must be wfm
        ext = value.split('.').pop()
        if ext != 'wfm':
            raise ivi.ValueNotSupportedException()
        # waveform must exist on arb
        self._load_catalog()
        if value not in self._catalog_names:
            raise ivi.ValueNotSupportedException()
        if not self._driver_operation_simulate:
            self._write(":ch%d:waveform \"%s\"" % (index+1, value))
        self._output_arbitrary_waveform[index] = value
    
    def _get_arbitrary_sample_rate(self):
        if not self._driver_operation_simulate and not self._get_cache_valid():
            resp = self._ask(":clock:frequency?").split(' ', 1)[1]
            self._arbitrary_sample_rate = float(resp)
            self._set_cache_valid()
        return self._arbitrary_sample_rate
    
    def _set_arbitrary_sample_rate(self, value):
        self._set_output_standard_waveform_frequency(self, value)
    
    def _get_arbitrary_waveform_number_waveforms_max(self):
        return self._arbitrary_waveform_number_waveforms_max
    
    def _get_arbitrary_waveform_size_max(self):
        return self._arbitrary_waveform_size_max
    
    def _get_arbitrary_waveform_size_min(self):
        return self._arbitrary_waveform_size_min
    
    def _get_arbitrary_waveform_quantum(self):
        return self._arbitrary_waveform_quantum
    
    def _arbitrary_waveform_clear(self, handle):
        pass
    
    def _arbitrary_waveform_create(self, data):
        y = None
        x = None
        if type(data) == list and type(data[0]) == float:
            # list
            y = array(data)
        elif type(data) == ndarray and len(data.shape) == 1:
            # 1D array
            y = data
        elif type(data) == ndarray and len(data.shape) == 2 and data.shape[0] == 1:
            # 2D array, hieght 1
            y = data[0]
        elif type(data) == ndarray and len(data.shape) == 2 and data.shape[1] == 1:
            # 2D array, width 1
            y = data[:,0]
        else:
            x, y = ivi.get_sig(data)
        
        if x is None:
            x = arange(0,len(y)) / 10e6
        
        if len(y) % self._arbitrary_waveform_quantum != 0:
            raise ivi.ValueNotSupportedException()
        
        xincr = ivi.rms(diff(x))
        
        # get unused handle
        self._load_catalog()
        have_handle = False
        while not have_handle:
            self._arbitrary_waveform_n += 1
            handle = "w%04d.wfm" % self._arbitrary_waveform_n
            have_handle = handle not in self._catalog_names
        self._write(":data:destination \"%s\"" % handle)
        self._write(":wfmpre:bit_nr 12")
        self._write(":wfmpre:bn_fmt rp")
        self._write(":wfmpre:byt_nr 2")
        self._write(":wfmpre:byt_or msb")
        self._write(":wfmpre:encdg bin")
        self._write(":wfmpre:pt_fmt y")
        self._write(":wfmpre:yzero 0")
        self._write(":wfmpre:ymult %e" % (2/(1<<12)))
        self._write(":wfmpre:xincr %e" % xincr)
        
        raw_data = b''
        
        for f in y:
            # clip at -1 and 1
            if f > 1.0: f = 1.0
            if f < -1.0: f = -1.0
            
            f = (f + 1) / 2
            
            # scale to 12 bits
            i = int(f * ((1 << 12) - 2) + 0.5) & 0x000fffff
            
            # add to raw data, MSB first
            raw_data = raw_data + struct.pack('>H', i)
        
        self._write_ieee_block(raw_data, ':curve ')
        
        return handle
    
    def _get_arbitrary_sequence_number_sequences_max(self):
        return self._arbitrary_sequence_number_sequences_max
    
    def _get_arbitrary_sequence_loop_count_max(self):
        return self._arbitrary_sequence_loop_count_max
    
    def _get_arbitrary_sequence_length_max(self):
        return self._arbitrary_sequence_length_max
    
    def _get_arbitrary_sequence_length_min(self):
        return self._arbitrary_sequence_length_min
    
    def _arbitrary_clear_memory(self):
        pass
    
    def _arbitrary_sequence_clear(self, handle):
        pass
    
    def _arbitrary_sequence_configure(self, index, handle, gain, offset):
        pass
    
    def _arbitrary_sequence_create(self, handle_list, loop_count_list):
        return "handle"
    
    def send_software_trigger(self):
        if not self._driver_operation_simulate:
            self._write("*TRG")
    
    def _get_output_burst_count(self, index):
        index = ivi.get_index(self._output_name, index)
        return self._output_burst_count[index]
    
    def _set_output_burst_count(self, index, value):
        index = ivi.get_index(self._output_name, index)
        value = int(value)
        self._output_burst_count[index] = value
    
    def _arbitrary_waveform_create_channel_waveform(self, index, data):
        handle = self._arbitrary_waveform_create(data)
        self._set_output_arbitrary_waveform(index, handle)
        return handle
    
    

