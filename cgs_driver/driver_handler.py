import re
from collections import OrderedDict

from common.driver_handler_base import DriverHandlerBase
from common.configuration_parser import ConfigurationParser
from common.resource_info import ResourceInfo


class cgs_driverDriverHandler(DriverHandlerBase):

    def __init__(self):
        DriverHandlerBase.__init__(self)
        self._switch_model = "CgsDriver"
        self._blade_model = "CgsDriver Blade"
        self._port_model = "CgsDriver Port"

        self.example_driver_setting = ConfigurationParser.get("driver_variable", "example_driver_setting")

    def login(self, address, username, password, command_logger=None):
	
	def_port = 2024

        address_data = re.search(r"(?P<host>[^:]*)"
                                 r":?(?P<port>[0-9]*)?",address, re.IGNORECASE)

        host = address_data.group("host")
	port = address_data.group("port")

        port = int(port) if port else int(def_port)

	try:
		self._session.connect(host, username, password, port, re_string=self._prompt)
	except:
		raise

    def get_resource_description(self, address, command_logger=None):
        
	depth = 0
        resource_info = ResourceInfo()
        resource_info.set_depth(depth)
        resource_info.set_address(address)

        error_map = OrderedDict([
            ("% Invalid", 'Can\'t get system details')
        ])

        command = 'show system details | nomore'
        system_details = self._session.send_command(command, re_string=self._prompt, error_map=error_map)
        model_name = re.search(r"Device Model[ ]*(.*?)\n", system_details, re.DOTALL).group(1)
        resource_info.set_model_name(model_name)
        resource_info.set_index(model_name)
        serial_number = re.search(r"Serial Number[ ]*(.*?)\n", system_details, re.DOTALL).group(1)
        resource_info.set_serial_number(serial_number)

	command = 'show ports | nomore'
        ports_details = self._session.send_command(command, re_string=self._prompt, error_map=error_map)

	blade_resource = ResourceInfo()
	blade_resource.set_depth(depth + 1)
	blade_resource.set_index(str(1))
	resource_info.add_child(1, blade_resource)

	src_ports_set = self.parse_filters_source_ports(command_logger)

        ports_list = re.search(r"Port.*?\n====.*?\n(.*)\n", ports_details, re.DOTALL).group(1).split("\n")

        for port in ports_list:

            port_id = re.search(r"(.*?)[ ]{1,}.*", port, re.DOTALL).group(1)

	    port_resource = ResourceInfo()
	    port_resource.set_depth(depth + 2)
	    port_resource.set_index(str(port_id))

	    if port_id in src_ports_set:
	    	port_resource.set_mapping("{}/1/{}".format(address, src_ports_set[port_id]))

	    blade_resource.add_child(port_id, port_resource)

	return resource_info.convert_to_xml()

    def parse_filters_source_ports(self, command_logger):

        error_map = OrderedDict([
            ("% Invalid", 'Can\'t get system details'),
            ("syntax error", 'Syntax error')
        ])

        command = 'show filters | nomore'
        filters_details = self._session.send_command(command, re_string=self._prompt, error_map=error_map)
        filters_list = re.search(r"Filter.*?\n====.*?\n(.*)\n", filters_details, re.DOTALL)

	src_ports_set = {}
	
	if filters_list is not None:
		filters_list = filters_list.group(1).split("\n")

        	for filter in filters_list:

            		filter_info = re.search(r"(?P<filter_id>.*?)[ ]{1,}"
                                    r".*?[]{1,}Enabled|Disabled[ ]{1,}.*?[ ]{1,}" # [name] Enable|disable action
                                    r"(?P<in_port>.*?)[ ]{1,}"
                                    r"(?P<out_port>.*?)[ ]{1,}"
                                    , filter)

	    		in_port = filter_info.group('in_port')
	    		out_port = filter_info.group('out_port')

	    		src_ports_set[out_port] = in_port	

	return src_ports_set


    def get_cgs_port(self, quali_port):
	# quali port format is: {ip},{blade},{port}[,{sub-port}]       
 
	# no breakout
	if len(quali_port) == 3:	
                cgs_port = quali_port[2]

        else:
		# breakout
		if len(quali_port) == 4:
                	cgs_port = "{}/{}".format(quali_port[2], quali_port[3])
		else:
			# error
			raise Exception			

	return cgs_port

	
    def map_bidi(self, src_port, dst_port, command_logger):
        self.map_uni(src_port, dst_port, command_logger)
	self.map_uni(dst_port, src_port, command_logger)


    def map_uni(self, src_port, dst_port, command_logger):
        
        error_map = OrderedDict([
            ("% Invalid", 'Can\'t get system details'),
	    ("syntax error", 'Syntax error')
        ])

	cgs_src_port = self.get_cgs_port(src_port)
	cgs_dst_port = self.get_cgs_port(dst_port)

	filter_add_command = "filters add input-ports {} output-ports {} action redirect; commit; exit".format(cgs_src_port, cgs_dst_port)

	try:
		error_msg = self._session.send_command("config", re_string=self._prompt, error_map=error_map)
	except:
		raise
	
	try:
		error_msg = self._session.send_command(filter_add_command, re_string=self._prompt, error_map=error_map)
        except:
                raise
	

    def map_clear_to(self, src_port, dst_port, command_logger):

	# delete all filters with outoput port = dst_port, src_port is ignored

        error_map = OrderedDict([
            ("% Invalid", 'Can\'t get system details'),
            ("syntax error", 'Syntax error')
        ])

        command = 'show filters | nomore'
	try:
        	filters_details = self._session.send_command(command, re_string=self._prompt, error_map=error_map)
	except:
		raise

	filters_list = re.search(r"Filter.*?\n====.*?\n(.*)\n", filters_details, re.DOTALL)

        if filters_list is not None:
                filters_list = filters_list.group(1).split("\n")

	filters_to_clear = []

        cgs_dst_port = self.get_cgs_port(dst_port)

        for filter in filters_list:

            filter_info = re.search(r"(?P<filter_id>.*?)[ ]{1,}"				# id
				    r".*?[]{1,}Enabled|Disabled[ ]{1,}.*?[ ]{1,}.*?[ ]{1,}" 	# [name] Enable|disable action vlan-action
                                    r"(?P<in_port>.*?)[ ]{1,}"					# in-ports
                                    r"(?P<out_port>.*?)[ ]{1,}"					# out-ports ...
                                    , filter)

	    if cgs_dst_port == filter_info.group('out_port'):
		filters_to_clear.append(filter_info.group('filter_id'))

	try:
		self._session.send_command("config", re_string=self._prompt, error_map=error_map)
	except:
		raise

	del_count = 0;
	for id in filters_to_clear:

		filter_id = int(id) - int(del_count)
        	filter_del_command = "filters delete filter {}".format(str(filter_id))
		try:
	        	self._session.send_command(filter_del_command, re_string=self._prompt, error_map=error_map)
		except:
			raise
		del_count += 1

	try:
		self._session.send_command("commit", re_string=self._prompt, error_map=error_map)
	except:
		raise

        try:
                self._session.send_command("exit", re_string=self._prompt, error_map=error_map)
        except:
                raise

    def map_clear(self, src_port, dst_port, command_logger):
	self.map_clear_to(src_port, dst_port, command_logger)

    def set_speed_manual(self, command_logger):
        """Set speed manual - skipped command

        :param command_logger: logging.Logger instance
        :return: None
        """
        pass
