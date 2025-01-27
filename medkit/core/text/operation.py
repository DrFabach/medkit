__all__ = [
    "ContextOperation",
    "NEROperation",
    "SegmentationOperation",
    "CustomTextOpType",
    "create_text_operation",
]

import abc
from enum import IntEnum
from typing import Any, Callable, List, Optional

from medkit.core.operation import Operation
from medkit.core.prov_tracer import ProvTracer
from medkit.core.text.annotation import Entity, Segment


class ContextOperation(Operation):
    """
    Abstract operation for context detection.
    It uses a list of segments as input for running the operation and creates attributes
    that are directly appended to these segments.
    """

    @abc.abstractmethod
    def run(self, segments: List[Segment]) -> None:
        raise NotImplementedError


class NEROperation(Operation):
    """
    Abstract operation for detecting entities.
    It uses a list of segments as input and produces a list of detected entities.
    """

    @abc.abstractmethod
    def run(self, segments: List[Segment]) -> List[Entity]:
        raise NotImplementedError


class SegmentationOperation(Operation):
    """
    Abstract operation for segmenting text.
    It uses a list of segments as input and produces a list of new segments.
    """

    @abc.abstractmethod
    def run(self, segments: List[Segment]) -> List[Segment]:
        raise NotImplementedError


class CustomTextOpType(IntEnum):
    """
    Enum class listing all supported function types for creating custom text operations

    Attributes
    ----------
    CREATE_ONE_TO_N
        Takes 1 data item, Return N new data items
    EXTRACT_ONE_TO_N
        Takes 1 data item, Return N existing data items
    FILTER
        Takes 1 data item, Returns True/False
    """

    CREATE_ONE_TO_N = 1
    EXTRACT_ONE_TO_N = 2
    FILTER = 3


class _CustomTextOperation(Operation):
    """
    Internal class representing a custom text operation.

    This class may be only instantiated by `create_text_operation`.

    It uses an user-defined function in the `run` method.
    It handles all provenance settings based on the function type.
    """

    def __init__(self, name: str, uid: Optional[str] = None):
        """

        Parameters
        ----------
        name
            Name of the operation used for provenance info
        uid
            Identifier of the operation
        """
        # Pass all arguments to super (remove self)
        init_args = locals()
        init_args.pop("self")
        super().__init__(**init_args)

        self._function = None
        self._function_type = None

    def set_prov_tracer(self, prov_tracer: ProvTracer):
        self._prov_tracer = prov_tracer

    def set_function(self, function: Callable, function_type: CustomTextOpType):
        """
        Assign a user-defined fonction to the operation
        Parameters
        ----------
        function
            User-defined function to be used in `run` method
        function_type
            Type of function.
            Supported values are defined in :class:`~medkit.core.text.CustomTextOpType`

        Returns
        -------

        """
        self._function = function
        self._function_type = function_type
        self.description.config["function_type"] = function_type.name
        # TODO: check signature according to type

    def run(self, all_input_data: List[Any]) -> List[Any]:
        """
        Run the custom operation on a list of input data and outputs a list of data

        This method uses the user-defined function depending on its type on a
        batch of data.

        Parameters
        ----------
        all_input_data
            List of input data

        Returns
        -------
        List[Any]
            Flat list of output data
        """
        assert self._function is not None
        assert self._function_type in set(CustomTextOpType)
        if self._function_type in [
            CustomTextOpType.CREATE_ONE_TO_N,
            CustomTextOpType.EXTRACT_ONE_TO_N,
        ]:
            return self._run_one_to_n_function(all_input_data, self._function_type)
        elif self._function_type == CustomTextOpType.FILTER:
            return self._run_filter_function(all_input_data)

    def _run_one_to_n_function(
        self, all_input_data: List[Any], function_type: CustomTextOpType
    ) -> List[Any]:
        all_output_data = []
        for input_data in all_input_data:
            output_data = self._function(input_data)
            if type(output_data) == list:
                all_output_data.extend(output_data)
            else:
                all_output_data.append(output_data)
            if (
                function_type == CustomTextOpType.CREATE_ONE_TO_N
                and self._prov_tracer is not None
            ):
                if type(output_data) == list:
                    for data in output_data:
                        self._prov_tracer.add_prov(
                            data_item=data,
                            op_desc=self.description,
                            source_data_items=[input_data],
                        )
                else:
                    self._prov_tracer.add_prov(
                        data_item=output_data,
                        op_desc=self.description,
                        source_data_items=[input_data],
                    )
        return all_output_data

    def _run_filter_function(self, all_input_data: List[Any]) -> List[Any]:
        all_output_data = []
        for input_data in all_input_data:
            checked = self._function(input_data)
            if checked:
                all_output_data.append(input_data)
        return all_output_data


def create_text_operation(
    function: Callable,
    function_type: CustomTextOpType,
    name: Optional[str] = None,
) -> _CustomTextOperation:
    """
    Function for instanciating a custom test operation from a user-defined function

    Parameters
    ----------
    function
        User-defined function
    function_type
        Type of function.
        Supported values are defined in :class:`~medkit.core.text.CustomTextOpType`
    name
        Name of the operation used for provenance info (default: function name)

    Returns
    -------
    operation
        An instance of a custom text operation
    """
    if name is None:
        name = function.__name__
    operation = _CustomTextOperation(name=name)
    operation.set_function(function=function, function_type=function_type)
    return operation
