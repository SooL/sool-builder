import typing as T

from structure import TabManager
from structure import ChipSet


class Component:
################################################################################
#                                   BUILDERS                                   #
################################################################################

	def __init__(self,
	             chips: T.Union[None, ChipSet] = None,
	             name: T.Union[None, str] = None,
	             brief: T.Union[None, str] = None,
				 parent: "Component" = None
	             ):
		self._name = name
		self.edited = True
		self.chips = ChipSet(chips)
		self.brief = brief
		self.parent = parent

	# def __contains__(self, item):
	# 	# noinspection PyTypeChecker
	# 	for child in self :
	# 		if child == item :
	# 			return True
	# 	return False
	#
	# def __getitem__(self, item):
	# 	# noinspection PyTypeChecker
	# 	for child in self :
	# 		if child == item :
	# 			return child
	# 	raise KeyError()

	def __eq__(self, other):
		return self.name == other.name

	@property
	def name(self):
		return self._name

	@name.setter
	def name(self,new):
		if new != self._name :
			self._name = new
			self.edited = True

	@property
	def have_been_edited(self):
		if self.edited :
			return True
		if hasattr(self,'__iter__') :
			for child in self :
				if child.edited :
					return True
		return False

	def finalize(self):
		if hasattr(self,'__iter__') :
			# noinspection PyTypeChecker
			for child in self :
				child.set_parent(self)
				child.finalize()
		self.chips.update_families()

	@property
	def computed_chips(self):
		out = ChipSet(self.chips)
		if hasattr(self,'__iter__'):
			child : Component
			for child in self :
				out.add(child.computed_chips)
		return out


	def set_parent(self, parent: "Component"):
		self.parent = parent

	def merge(self, other: "Component"):
		self.chips.add(other.chips)

################################################################################
#                            STRING REPRESENTATIONS                            #
################################################################################

	def __str__(self) -> T.Union[None, str]:
		return self.name

	def __repr__(self):
		return str(self)

	@property
	def alias(self) -> T.Union[None, str] :
		"""
		Returns the hierarchy up to this point.
		Used as the defined pre-processor constant when needed.
		:returns: the full name of the Component. Usually "<parent_alias>_<name>"
		"""
		if self.parent is None : return self.name
		else :
			parent_alias: T.Union[str, None] = self.parent.alias
			if parent_alias is None : return self.name
			elif self.name is None  : return parent_alias
			else                    : return parent_alias + "_" + self.name

################################################################################
#                              DEFINE / UNDEFINE                               #
################################################################################

	def needs_define(self) -> bool :
		"""
		Checks whether or not the Component needs to have its alias defined.
		:returns: True if the Component needs to have its alias defined
		"""
		return (self.name is not None) and\
		       (self.parent is not None) and\
		       (self.chips != self.parent.chips)

	def define(self) -> T.Union[str,None] :
		if self.needs_define() :
			return f"#define {self.alias}"
		else :
			return None

	def define_not(self) -> T.Union[str, None] :
		return None

	def undefine(self) -> T.Union[None, str] :
		if self.needs_define() :
			return f"#undef {self.alias}"
		else :
			return None

################################################################################
#                                    USAGE                                     #
################################################################################
	def declare(self, indent: TabManager = TabManager()) -> T.Union[None,str] :
		return "None"



