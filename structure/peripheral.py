import xml.etree.ElementTree as ET
import typing as T
import logging
from structure.register import Register
from structure.chipset import ChipSet
from structure.utils import get_node_text, default_tabmanager

# Must not be imported (cyclic import issues)
# from structure.group import Group

from copy import copy, deepcopy
# from deprecated import deprecated
logger = logging.getLogger()


class Peripheral:
	def __init__(self, xml_base : ET.Element, chip : ChipSet = ChipSet()):
		"""
		Build a Peripheral representation based upon XML node.
		If relevant, build all registers.
		:param xml_base: xml <peripheral> node, extracted from SVD file
		"""
		self.xml_data: ET.Element = xml_base

		self.name: str = None
		brief: str = get_node_text(self.xml_data, "description")\
			.lower()\
			.replace("-", " ")\
			.replace("\n", " ")
		self.brief = " ".join(brief.split())

		self.group: "Group" = None
		self.registers: T.List[Register] = list()
		self.chips = chip

		self.variance_id: str = None
		self.instances: T.List[PeripheralInstance] = list()
		self.mappings: T.List[PeripheralMapping] = list()

		self.fill_from_xml()

		# self.address = int(self.xml_data.find("baseAddress").text,0)

	def fill_from_xml(self):
		new_mapping = PeripheralMapping(self, self.chips)

		for xml_reg in self.xml_data.findall("registers/register"):
			new_register = Register(xml_reg, self.chips)
			self.registers.append(new_register)
			new_mapping.register_mapping[int(get_node_text(xml_reg, "addressOffset"), 0)] = new_register
		self.mappings.append(new_mapping)

########################################################################################################################
#                                                      OPERATORS                                                       #
########################################################################################################################

	def __repr__(self):
		return f"{str(self.name):20s} : {str(self.chips)}"

	def __eq__(self, other):
		if isinstance(other, Peripheral) :
			return (self.name == other.name and
					self.brief == other.brief and
					self.mapping_equivalent_to(other))

		elif isinstance(other, str) :
			return other == self.name
		else :
			raise TypeError()

	def __getitem__(self, item) -> Register:
		if isinstance(item, Register):
			for register in self.registers :
				if item == register :
					return register
			raise KeyError()
		elif isinstance(item,str) :
			for register in self.registers :
				if register.name == item :
					return register
			raise KeyError()
		elif isinstance(item,int) :
			return self.registers[item]
		else :
			raise TypeError()

	@property
	def computed_chips(self) -> ChipSet:
		"""
		Return chipset based upon content
		:return:
		"""
		out = ChipSet()
		for map in self.mappings :
			out.add(map.computed_chips)
		return out
	
	def cleanup(self):
		for m in self.mappings :
			m.cleanup()
		try:
			del self.xml_data
		except AttributeError:
			pass
########################################################################################################################
#                                                 INSTANCES MANAGEMENT                                                 #
########################################################################################################################

	def add_instance(self, instance : "PeripheralInstance"):
		self.chips.add(instance.chips)
		for inst in self.instances :
			if instance == inst :
				inst.chips.add(instance.chips)
				return
		self.instances.append(instance)

	# Todo merge into add_instance, cf chips.
	def add_instances(self, instances):
		for inst in instances :
			self.add_instance(inst)

########################################################################################################################
#                                                  PERIPHERAL MERGING                                                  #
########################################################################################################################

	def mapping_equivalent_to(self,other : "Peripheral") -> bool :
		"""
		Check if the mapping is equivalent between self and other.
		That is if both peripheral are equals and their contents recursively are too.
		:param other:
		"""
		for register in self :
			if register not in other or not other[register].mapping_equivalent_to(register) :
				return False
		return True

	def compatible(self, other: "Peripheral") -> bool :
		if self.mapping_equivalent_to(other) :
			return True

		for pos in other.mappings[0].register_mapping :
			if pos in self.mappings[0].register_mapping :
				if not other.mappings[0].register_mapping[pos]\
						.compatible(self.mappings[0].register_mapping[pos]):
					return False
		return True
	
	def merge_peripheral(self,other : "Peripheral"):
		"""
		Will merge another peripheral to this one. Adding instances and mapping.
		
		:param other: The peripheral to merge into this one.
		:return:
		"""
		equivalent_mapping = None
		equivalent_instance = None

		# Merge chips
		self.chips.add(other.chips)

		# Merge registers
		for reg in other:
			if reg.name in self:

				local_register = self[reg.name]
				for field in reg:
					local_register.add_field(field)
			else:
				self.registers.append(reg)

		# If a mapping, equivalent to the one of the other peripheral, is found, we will use it
		# In this case, we only have to append the chip(s) of the other peripheral.
		if len(other.mappings) != 1:
			logger.error("multiple mappings on new peripheral")

		for other_mapping in other.mappings:
			merge_done: bool = False
			for m in self.mappings:
				if m.merge_mapping(other_mapping):
					self.chips.add(other_mapping.chips)
					merge_done = True
					break
			
			if not merge_done :
				self.mappings.append(other_mapping)
				self.chips.add(other_mapping.chips)
				
		# Same principle with instances
		for other_instance in other.instances :

			for instance in self.instances:
				if instance == other_instance:
					equivalent_instance = instance
					break

			# Same for instances
			if equivalent_instance is None:
				equivalent_instance = PeripheralInstance(self,
														 other_instance.name,
														 other_instance.address,
														 other.chips)
				self.instances.append(equivalent_instance)
				self.chips.add(other_instance.chips)
			else:
				equivalent_instance.chips.add(other.chips)
				self.chips.add(other_instance.chips)

	def finalize(self):
		self.instances = sorted(self.instances,key=lambda x : (x.name,len(x.chips.chips),x.address))
		for register in self :
			register.finalize()

	def cpp_output(self):

		# default_tabmanager.increment()
		out =""
		out += (f"{default_tabmanager}class {self.name}\n"
				f"{default_tabmanager}{{")
		out += f"{default_tabmanager + 1}//Registers definition\n\n"
		for reg in self.registers:
			out += reg.cpp_output()

		out += f"\n\n{default_tabmanager + 1}//Mappings needs conditions\n\n"
		for mapping in self.mappings:
			out += mapping.cpp_output() + "\n"

		out += f"{default_tabmanager}}}"
		return out



########################################################################################################################
#                                                 PERIPHERAL MAPPING                                                 #
########################################################################################################################


class PeripheralMapping:
	def __init__(self, reference: Peripheral, chips: ChipSet):
		self.reference = reference
		self.name: str = None # the name will be determined when the whole structure is built
		self.chips: ChipSet = chips
		
		self.register_mapping: T.Dict[int, Register] = dict()
	
	def __repr__(self):
		return ", ".join([f"{pos:3d}: {self.register_mapping[pos]}" for pos in self.register_mapping.keys()]) + " : " \
			   + str(self.chips)
		
	def __eq__(self, other):
		if isinstance(other, PeripheralMapping):
			positions = self.register_mapping.keys()
			if len(set(positions).symmetric_difference(set(other.register_mapping.keys()))) != 0:
				return False
			for pos in positions :
				if self.register_mapping[pos] != other.register_mapping[pos]:
					return False
			return True
		elif isinstance(other, Peripheral):
			for mapping in other.mappings:
				if mapping == self:
					return True
		else:
			raise TypeError()
		return False

	@property
	def computed_chips(self) -> ChipSet:
		"""
		Return chipset based upon content
		:return:
		"""
		out = ChipSet()
		for key,reg in self.register_mapping.items() :
			out.add(reg.computed_chips)
		return out

	@property
	def memory_bit_space(self) -> T.Set[int]:
		out = set()
		for addr, reg in self.register_mapping.items() :
			out.update(range(addr*8,(addr*8) + reg.size))
		return out
	
	@property
	def memory_byte_space(self) -> T.Set[int]:
		out = set()
		for addr, reg in self.register_mapping.items() :
			out.update(range(addr,addr + int(reg.size/8)))
		return out
	
	def subset(self,other : "PeripheralMapping") -> bool:
		"""
		Check if the current mapping is a subset of the given mapping
		:param other:
		"""
		for pos,reg in self.register_mapping.items() :
			if pos not in other.register_mapping :
				return False
			if reg != other.register_mapping[pos] :
				return False
		return True

	def superset(self, other: "PeripheralMapping") -> bool:
		return other.subset(self)

	def cleanup(self):
		for p,m in self.register_mapping.items():
			m.cleanup()
			
	def merge_mapping(self, other : "PeripheralMapping") -> bool:
		"""
		This function will merge the other mapping into the current one if
		the other one can fit within the current one. That is either :
		
		 - Same register name at same position
		 - Hole in the current register to be filled by other.
		
		This function will not edit anything unless the merge is possible.
		
		:param other: mapping to merge to the current one.
		:return: True if merged ok, false otherwise
		"""
		for addr,reg  in other.register_mapping.items() :
			if addr in self.register_mapping:
				local_reg = self.register_mapping[addr]
				if reg.name != local_reg.name :
					if reg.mapping_equivalent_to(local_reg) :
						local_name = local_reg.name
						other_name = reg.name
						new_name = local_name if len(local_name) <= len(other_name) else other_name
						logger.warning(f"Fixing register name : same mapping for various names in "
									   f"{self.reference.name:10s}. Local : {local_name:15s} - Other : {other_name:15s}")
						local_reg.name = new_name
						reg.name = new_name
					else :
						return False
		
		for a, reg in other.register_mapping.items() :
			if a in self.register_mapping :
				self.register_mapping[a].merge_register(reg)
			else :
				self.register_mapping[a] = reg
		self.chips.add(other.chips)
		
		return True

	def cpp_output(self):
		out = ""
		default_tabmanager.increment()
		for addr in sorted(self.register_mapping.keys()) :
			reg = self.register_mapping[addr]
			out += f"{default_tabmanager}{f'{reg.name}_t':20s}\t{reg.name};\n"

		default_tabmanager.decrement()
		return out
		
########################################################################################################################
#                                                 PERIPHERAL INSTANCE                                                  #
########################################################################################################################

class PeripheralInstance :
	def __init__(self, reference : Peripheral, name : str, address : int, chips: ChipSet):
		self.reference : Peripheral = reference
		self.name = name
		self.address = address
		self.chips = chips
	
	def __repr__(self):
		return f"{self.name:20s} @ 0x{self.address:08X} {self.chips}"
	
	def __eq__(self, other):
		if isinstance(other, PeripheralInstance) :
			return self.name == other.name and self.address == other.address
		elif isinstance(other, Peripheral) :
			for instance in other.instances :
				if instance == self :
					return True
		else :
			raise TypeError()
		return False

	def computed_chips(self) -> ChipSet:
		"""
		Return chipset based upon content
		:return:
		"""
		return self.chips