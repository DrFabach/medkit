__all__ = ["EDSCleaner"]

import dataclasses
from typing import List

from medkit.core import Operation
from medkit.core.text import Segment, utils

# predefined configuration for french documents
_FR_CIVIL_TITLES = ["M", "Mme", "Mlle", "Mr", "Pr", "Dr", "Mde"]
_FR_PREPOSITIONS_AFTER = [
    "de",
    "par",
    "le",
    "du",
    "la",
    "les",
    "des",
    "un",
    "une",
    "ou",
    "pour",
    "avec",
]
_FR_KEYWORDS_BEFORE = ["pour", "avec", "et"]


@dataclasses.dataclass(frozen=True)
class DefaultConfig:
    output_label = "CLEAN_TEXT"
    keep_endlines = False
    handle_parentheses_eds = True
    handle_points_eds = True


class EDSCleaner(Operation):
    """
    EDS pre-processing annotation module

    This module is a non-destructive module allowing to remove and clean selected points
    and newlines characters. It respects the span modification by creating a new
    text-bound annotation containing the span modification information from input text.

    """

    def __init__(
        self,
        output_label: str = DefaultConfig.output_label,
        keep_endlines: bool = DefaultConfig.keep_endlines,
        handle_parentheses_eds: bool = DefaultConfig.handle_parentheses_eds,
        handle_points_eds: bool = DefaultConfig.handle_points_eds,
        uid: str = None,
    ):
        """
        Instantiate the endlines handler.

        Parameters
        ----------
        output_label
            The output label of the created annotations.
            Default: "CLEAN_TEXT" (cf.DefaultConfig)
        keep_endlines:
            If True, modify multiple endlines using `.\\n` as a replacement.
            If False (default), modify multiple endlines using whitespaces (`.\\s`) as a replacement.
        handle_parentheses_eds:
            If True (default), modify the text near to parentheses or keywords according to
            predefined rules for french documents
            If False, the text near to parentheses or keywords is not modified
        handle_points_eds:
            Modify points near to predefined keywords for french documents
            If True (default), modify the points near to keywords
            If False, the points near to keywords is not modified
        uid
            Identifier of the pre-processing module
        """
        # Pass all arguments to super (remove self)
        init_args = locals()
        init_args.pop("self")
        super().__init__(**init_args)

        self.output_label = output_label
        self.keep_endlines = keep_endlines
        self.handle_parentheses_eds = handle_parentheses_eds
        self.handle_points_eds = handle_points_eds

    def run(self, segments: List[Segment]) -> List[Segment]:
        """
        Run the module on a list of segments provided as input
        and returns a new list of segments.

        Parameters
        ----------
        segments
            List of segments to normalize

        Returns
        -------
        List[~medkit.core.text.Segment]:
            List of cleaned segments.
        """
        return [
            norm_segment
            for segment in segments
            for norm_segment in self._clean_segment_text(segment)
        ]

    def _clean_segment_text(self, segment: Segment):
        """
        Clean up a segment non-destructively, remove points between numbers and  upper case letters.
        Then remove multiple whitespaces or newline characters.
        Finally, modify parentheses or point after keywords if necessary.
        """
        text = segment.text
        spans = segment.spans

        # modify points characters
        text, spans = utils.replace_point_in_uppercase(text, spans)
        text, spans = utils.replace_point_in_numbers(text, spans)

        # modify newline character
        text, spans = utils.clean_newline_character(
            text=text, spans=spans, keep_endlines=self.keep_endlines
        )
        # modify all whitespaces characters
        text, spans = utils.clean_multiple_whitespaces_in_sentence(text, spans)

        # modify parentheses using predefined rules for french documents
        if self.handle_parentheses_eds:
            text, spans = utils.clean_parentheses_eds(text, spans)

        if self.handle_points_eds:
            # replace the character `.` after and before certain keywords
            # after the title of a person (i.e. M. or Mrs.)
            text, spans = utils.replace_point_after_keywords(
                text=text,
                spans=spans,
                keywords=_FR_CIVIL_TITLES,
                strict=True,
            )
            # after certain prepositions (`du` . patient)
            text, spans = utils.replace_point_after_keywords(
                text=text,
                spans=spans,
                keywords=_FR_PREPOSITIONS_AFTER,
                strict=False,
            )
            # before certain prepositions (venue   . `avec`)
            text, spans = utils.replace_point_before_keywords(
                text=text, spans=spans, keywords=_FR_KEYWORDS_BEFORE
            )

        # create ann with the clean text
        clean_text = Segment(label=self.output_label, spans=spans, text=text)

        if self._prov_tracer is not None:
            self._prov_tracer.add_prov(
                clean_text, self.description, source_data_items=[segment]
            )

        yield clean_text
