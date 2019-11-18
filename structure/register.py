import typing as T
import xml.etree.ElementTree as ET

import logging

from structure import Field
from structure import RegisterVariant
from structure import get_node_text, TabManager
from structure import ChipSet
from structure import Component
from structure.utils import DefinesHandler, fill_periph_hole

logger = logging.getLogger()

################################################################################
################################### REGISTER ###################################
################################################################################
REGISTER_DEFAULT_SIZE: int = 32
REGISTER_DECLARATION: str = """{indent}struct {reg.name}_t: Reg{reg.size}_t /// {reg.brief}
{indent}{{
{variants}{indent}\t//SOOL-{reg.alias}-DECLARATIONS
{indent}}};
"""

class Register(Component) :

################################################################################
#                                 CONSTRUCTORS                                 #
################################################################################

	@staticmethod
	def create_from_xml(chips: ChipSet, xml_data: ET.Element) -> "Register":
		name = get_node_text(xml_data, "name").strip(None)
		brief = get_node_text(xml_data, "description").strip(None)
		access = get_node_text(xml_data, "access").strip(None)

		# check if displayName is different from name
		disp_name = get_node_text(xml_data, "displayName").strip(None)
		if disp_name != name :
			logger.warning(f"Register name and display discrepancy :"
			               f" {name} displayed as {disp_name}")

		read_size_value = get_node_text(xml_data, "size")
		size = REGISTER_DEFAULT_SIZE if (read_size_value == str()) \
			else int(read_size_value, 0)

		# self.rst = int(get_node_text(xml_base,"resetValue"),0)  # Is a mask
		register = Register(chips=chips, name=name, brief=brief,
		                    size=size, access=access)

		xml_fields = xml_data.findall("fields/field")
		if xml_fields is not None :
			for xml_field in xml_fields :
				register.add_field(field=Field.create_from_xml(chips, xml_field), in_xml_node=True)

		return register

	def __init__(self,
	             chips: T.Union[ChipSet, None] = None,
	             name: T.Union[str, None] = None,
	             brief: T.Union[str, None] = None,
	             size: int = 32,
	             access: T.Union[str, None] = None) :
		super().__init__(chips=chips, name=name, brief=brief)
		self._size = size
		self.access = access
		self.variants: T.List[RegisterVariant] = list()

################################################################################
#                                  OPERATORS                                   #
################################################################################

	def __iter__(self) :
		return iter(self.variants)

	def __contains__(self, item) :
		if isinstance(item, RegisterVariant) :
			return super().__contains__(item)
		elif isinstance(item,Field) :
			for var in self :
				if item in var  :
					return True
			return False
		raise TypeError()

	def __getitem__(self, item: str) -> Field:
		result: T.Union[Field, None] = None
		for var in self :
			if item in var :
				return var[item]
		raise KeyError()

	def __eq__(self, other):
		if isinstance(other, Register) :
			for var in self :
				if var.for_template :
					continue
				for field in var :
					if field not in other :
						return False
			for var in other :
				if var.for_template :
					continue
				for field in var :
					if field not in self :
						return False
			return True
		raise TypeError(f"Provided type {type(other)}")

	@property
	def has_template(self) -> bool :
		for v in self :
			if v.for_template :
				return True
		return False

	@property
	def size(self) -> int :
		return self._size

	@size.setter
	def size(self, new_size: int) :
		self._size = new_size

################################################################################
#                         FIELDS & VARIANTS MANAGEMENT                         #
################################################################################

	def add_field(self, field: Field, in_xml_node: bool = False) :
		self.chips.add(field.chips)

		var: T.Optional[RegisterVariant] = None
		for v in self.variants :
			if (not in_xml_node) and v.for_template :
				continue # don't add single fields to template variants

			if field in v :
				v[field].inter_svd_merge(field)
				return
			if v.has_room_for(field) :
				var = v
				break

		if var is None :
			var = RegisterVariant()
			self.add_variant(var)
		var.add_field(field)

	def add_variant(self, variant: RegisterVariant) :
		self.variants.append(variant)
		variant.set_parent(self)
		self.edited = True

	def intra_svd_merge(self, other: "Register") :
		for v in other :
			self.add_variant(v)

	def inter_svd_merge(self, other: "Register"):
		super().inter_svd_merge(other)
		if other.size > self.size :
			self.size = other.size
		for o_v in other :
			placed = False
			for s_v in self :
				if o_v == s_v :
					s_v.inter_svd_merge(o_v)
					placed = True
					break
			if not placed :
				if o_v.for_template :
					self.add_variant(o_v)
				else :
					for f in o_v :
						self.add_field(f)

	def before_svd_compile(self, parent_corrector):
		old_name = self.name
		super().before_svd_compile(parent_corrector)
		if self.name != old_name :
			for m in self.parent.mappings :
				for elmt in m :
					if elmt.component is self and elmt.name == old_name :
						elmt.name = self.name

	def svd_compile(self):
		super().svd_compile()

		var_index = 0
		while var_index < len(self.variants)-1 :
			var_offset = 1
			while var_index + var_offset < len(self.variants) :
				if self.variants[var_index] == self.variants[var_index + var_offset] :
					for f in self.variants[var_index + var_offset] :
						self.variants[var_index][f].intra_svd_merge(f)
					self.variants.pop(var_index + var_offset)
					self.edited = True
				else :
					var_offset += 1
			var_index += 1

################################################################################
#                          DEFINE, UNDEFINE & DECLARE                          #
################################################################################

	@property
	def undefine(self) -> True:
		return False

	@property
	def defined_value(self) -> T.Union[str, None]:
		return None

	def declare(self, indent: TabManager = TabManager()) -> T.Union[None,str] :
		out: str = ""
		is_union = len(self.variants) > 1
		if is_union :
			indent.increment()
			out += f"{indent}union\n{indent}{{\n"

		indent.increment()
		out += "".join(
			map(lambda v : v.declare(indent), filter(lambda var: not var.for_template, self.variants)))

		if self.has_template :
			out += f"{indent}tmpl::{self.name}_t;\n"

		indent.decrement()

		if is_union :
			out += f"{indent}}};\n"
			indent.decrement()

		out = REGISTER_DECLARATION.format(
			indent=indent, reg=self,
			variants=out)
		if self.needs_define :
			out = f"{indent}#ifdef {self.defined_name}\n{out}{indent}#endif\n"
		return out
